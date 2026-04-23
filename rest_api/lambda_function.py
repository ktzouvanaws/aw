"""
Betting & Gaming REST API — Lambda handler (DynamoDB-backed)

Deployed behind API Gateway as a proxy integration.
All data is read from and persisted to DynamoDB tables.
"""

import json
import random
import uuid
import os
import boto3
from datetime import datetime
from decimal import Decimal
from boto3.dynamodb.conditions import Key


# --- DynamoDB setup ---

REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_PREFIX = os.environ.get("TABLE_PREFIX", "Betting")

dynamodb = boto3.resource("dynamodb", region_name=REGION)

sports_table = dynamodb.Table(f"{TABLE_PREFIX}Sports")
events_table = dynamodb.Table(f"{TABLE_PREFIX}Events")
odds_table = dynamodb.Table(f"{TABLE_PREFIX}Odds")
bets_table = dynamodb.Table(f"{TABLE_PREFIX}Bets")
accounts_table = dynamodb.Table(f"{TABLE_PREFIX}Accounts")
promotions_table = dynamodb.Table(f"{TABLE_PREFIX}Promotions")
transactions_table = dynamodb.Table(f"{TABLE_PREFIX}Transactions")
tickets_table = dynamodb.Table(f"{TABLE_PREFIX}SupportTickets")

DEFAULT_ACCOUNT_ID = "default"


# --- Helpers ---

class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types returned by DynamoDB."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)


def respond(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, cls=DecimalEncoder),
    }


def _get_account(account_id=None):
    """Get an account by ID. Falls back to DEFAULT_ACCOUNT_ID if not provided."""
    aid = account_id or DEFAULT_ACCOUNT_ID
    result = accounts_table.get_item(Key={"accountId": aid})
    if "Item" not in result:
        return None
    return result["Item"]


def _mock_score(sport):
    if sport == "football":
        return f"{random.randint(0, 3)}-{random.randint(0, 3)}"
    elif sport == "basketball":
        return f"{random.randint(70, 120)}-{random.randint(70, 120)}"
    elif sport == "tennis":
        return f"{random.randint(0, 6)}-{random.randint(0, 6)}"
    elif sport == "esports":
        return f"{random.randint(0, 2)}-{random.randint(0, 2)}"
    return "N/A"


# --- Lambda handler ---

def lambda_handler(event, context):
    method = event.get("httpMethod", "GET")
    path = event.get("path", "/")
    body = {}
    if event.get("body"):
        body = json.loads(event["body"])

    # --- Routes ---

    # GET /sports
    if path == "/sports" and method == "GET":
        result = sports_table.scan()
        return respond(200, {"sports": result["Items"]})

    # GET /sports/{sportId}/events
    if path.startswith("/sports/") and path.endswith("/events") and method == "GET":
        sport_id = path.split("/")[2]
        result = events_table.query(
            KeyConditionExpression=Key("sportId").eq(sport_id)
        )
        events = result["Items"]
        if not events:
            return respond(404, {"error": f"No events found for sport '{sport_id}'"})
        return respond(200, {"sport": sport_id, "events": events})

    # GET /events/{eventId}/odds
    if path.startswith("/events/") and path.endswith("/odds") and method == "GET":
        event_id = path.split("/")[2]
        result = odds_table.get_item(Key={"eventId": event_id})
        if "Item" not in result:
            return respond(404, {"error": f"No odds found for event '{event_id}'"})

        odds_item = result["Item"]
        odds = odds_item.get("odds", {})

        # Find event info for display name
        event_name = "Unknown"
        all_events = events_table.scan()["Items"]
        for evt in all_events:
            if evt["id"] == event_id:
                event_name = f"{evt['home']} vs {evt['away']}"
                break

        return respond(200, {
            "eventId": event_id,
            "event": event_name,
            "odds": odds,
            "lastUpdated": datetime.utcnow().isoformat() + "Z",
        })

    # GET /events/live
    if path == "/events/live" and method == "GET":
        result = events_table.query(
            IndexName="StatusIndex",
            KeyConditionExpression=Key("status").eq("live")
        )
        live = []
        for evt in result["Items"]:
            live.append({
                "eventId": evt["id"],
                "sport": evt["sportId"],
                "home": evt["home"],
                "away": evt["away"],
                "score": _mock_score(evt["sportId"]),
            })
        return respond(200, {"liveEvents": live})

    # POST /bets
    if path == "/bets" and method == "POST":
        event_id = body.get("eventId")
        selection = body.get("selection")
        stake = body.get("stake", 0)
        account_id = body.get("accountId", DEFAULT_ACCOUNT_ID)

        if not event_id or not selection:
            return respond(400, {"error": "eventId and selection are required"})

        # Get odds from DynamoDB
        odds_result = odds_table.get_item(Key={"eventId": event_id})
        if "Item" not in odds_result:
            return respond(404, {"error": f"Event '{event_id}' not found"})

        odds = odds_result["Item"].get("odds", {})
        if selection not in odds:
            return respond(400, {"error": f"Invalid selection '{selection}'", "validSelections": list(odds.keys())})
        if stake <= 0:
            return respond(400, {"error": "Stake must be greater than 0"})

        # Get account balance
        account = _get_account(account_id)
        if not account:
            return respond(404, {"error": f"Account '{account_id}' not found"})
        balance = float(account["balance"])

        if stake > balance:
            return respond(400, {"error": f"Insufficient balance: ${balance:.2f}"})

        # Place the bet
        bet_id = f"bet-{uuid.uuid4().hex[:8]}"
        selected_odds = float(odds[selection])
        potential_return = round(stake * selected_odds, 2)
        new_balance = round(balance - stake, 2)

        bet = {
            "betId": bet_id,
            "accountId": account_id,
            "eventId": event_id,
            "selection": selection,
            "odds": Decimal(str(selected_odds)),
            "stake": Decimal(str(stake)),
            "potentialReturn": Decimal(str(potential_return)),
            "status": "active",
            "placedAt": datetime.utcnow().isoformat() + "Z",
        }

        # Write bet to DynamoDB
        bets_table.put_item(Item=bet)

        # Update account balance
        accounts_table.update_item(
            Key={"accountId": account_id},
            UpdateExpression="SET balance = :b",
            ExpressionAttributeValues={":b": Decimal(str(new_balance))},
        )

        return respond(201, {
            "message": "Bet placed successfully",
            "bet": bet,
            "remainingBalance": new_balance,
        })

    # GET /bets
    if path == "/bets" and method == "GET":
        result = bets_table.scan()
        bets = result["Items"]
        total_staked = sum(float(b["stake"]) for b in bets)
        return respond(200, {
            "bets": bets,
            "totalBets": len(bets),
            "totalStaked": round(total_staked, 2),
        })

    # GET /bets/{betId}
    if path.startswith("/bets/") and method == "GET" and path.count("/") == 2:
        bet_id = path.split("/")[2]
        result = bets_table.get_item(Key={"betId": bet_id})
        if "Item" not in result:
            return respond(404, {"error": f"Bet '{bet_id}' not found"})
        return respond(200, {"bet": result["Item"]})

    # GET /account/balance
    if path == "/account/balance" and method == "GET":
        query_params = event.get("queryStringParameters") or {}
        account_id = query_params.get("accountId", DEFAULT_ACCOUNT_ID)
        account = _get_account(account_id)
        if not account:
            return respond(404, {"error": f"Account '{account_id}' not found"})

        # Count active bets for this account
        bets_result = bets_table.query(
            IndexName="AccountIndex",
            KeyConditionExpression=Key("accountId").eq(account_id)
        )
        pending = len([b for b in bets_result["Items"] if b.get("status") == "active"])

        return respond(200, {
            "accountId": account_id,
            "balance": account["balance"],
            "currency": account.get("currency", "USD"),
            "pendingBets": pending,
        })

    # GET /promotions
    if path == "/promotions" and method == "GET":
        result = promotions_table.scan()
        return respond(200, {"promotions": result["Items"]})

    # --- Customer Support Routes ---

    # GET /customers/{accountId}
    if path.startswith("/customers/") and method == "GET" and path.count("/") == 2:
        account_id = path.split("/")[2]
        result = accounts_table.get_item(Key={"accountId": account_id})
        if "Item" not in result:
            return respond(404, {"error": f"Customer '{account_id}' not found"})
        return respond(200, {"customer": result["Item"]})

    # GET /customers/{accountId}/bets
    if path.startswith("/customers/") and path.endswith("/bets") and method == "GET":
        account_id = path.split("/")[2]
        result = bets_table.query(
            IndexName="AccountIndex",
            KeyConditionExpression=Key("accountId").eq(account_id)
        )
        return respond(200, {"accountId": account_id, "bets": result["Items"], "totalBets": len(result["Items"])})

    # GET /customers/{accountId}/transactions
    if path.startswith("/customers/") and path.endswith("/transactions") and method == "GET":
        account_id = path.split("/")[2]
        result = transactions_table.query(
            KeyConditionExpression=Key("accountId").eq(account_id)
        )
        return respond(200, {"accountId": account_id, "transactions": result["Items"]})

    # GET /support/tickets
    if path == "/support/tickets" and method == "GET":
        result = tickets_table.scan()
        return respond(200, {"tickets": result["Items"], "totalTickets": len(result["Items"])})

    # GET /support/tickets/{ticketId}
    if path.startswith("/support/tickets/") and method == "GET" and path.count("/") == 3:
        ticket_id = path.split("/")[3]
        result = tickets_table.get_item(Key={"ticketId": ticket_id})
        if "Item" not in result:
            return respond(404, {"error": f"Ticket '{ticket_id}' not found"})
        return respond(200, {"ticket": result["Item"]})

    # GET /customers/{accountId}/tickets
    if path.startswith("/customers/") and path.endswith("/tickets") and method == "GET":
        account_id = path.split("/")[2]
        result = tickets_table.query(
            IndexName="AccountIndex",
            KeyConditionExpression=Key("accountId").eq(account_id)
        )
        return respond(200, {"accountId": account_id, "tickets": result["Items"]})

    # POST /support/tickets
    if path == "/support/tickets" and method == "POST":
        account_id = body.get("accountId")
        subject = body.get("subject")
        description = body.get("description", "")
        category = body.get("category", "general")
        priority = body.get("priority", "medium")

        if not account_id or not subject:
            return respond(400, {"error": "accountId and subject are required"})

        ticket_id = f"tkt-{uuid.uuid4().hex[:8]}"
        now = datetime.utcnow().isoformat() + "Z"

        ticket = {
            "ticketId": ticket_id,
            "accountId": account_id,
            "subject": subject,
            "description": description,
            "category": category,
            "priority": priority,
            "status": "open",
            "createdAt": now,
            "updatedAt": now,
        }
        tickets_table.put_item(Item=ticket)
        return respond(201, {"message": "Ticket created", "ticket": ticket})

    return respond(404, {"error": f"Route not found: {method} {path}"})
