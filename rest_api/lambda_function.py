"""
Mock Betting & Gaming REST API — Lambda handler

Deployed behind API Gateway as a proxy integration.
"""

import json
import random
import uuid
from datetime import datetime

# --- Mock Data ---

SPORTS = [
    {"id": "football", "name": "Football", "activeEvents": 24},
    {"id": "basketball", "name": "Basketball", "activeEvents": 18},
    {"id": "tennis", "name": "Tennis", "activeEvents": 32},
    {"id": "horse_racing", "name": "Horse Racing", "activeEvents": 12},
    {"id": "esports", "name": "Esports", "activeEvents": 8},
]

EVENTS = {
    "football": [
        {"id": "evt-001", "home": "Arsenal", "away": "Chelsea", "league": "Premier League", "kickoff": "2026-04-25T15:00:00Z", "status": "upcoming"},
        {"id": "evt-002", "home": "Barcelona", "away": "Real Madrid", "league": "La Liga", "kickoff": "2026-04-25T20:00:00Z", "status": "upcoming"},
        {"id": "evt-003", "home": "Bayern Munich", "away": "Dortmund", "league": "Bundesliga", "kickoff": "2026-04-26T17:30:00Z", "status": "upcoming"},
    ],
    "basketball": [
        {"id": "evt-010", "home": "Lakers", "away": "Celtics", "league": "NBA", "kickoff": "2026-04-25T19:30:00Z", "status": "live"},
        {"id": "evt-011", "home": "Warriors", "away": "Bucks", "league": "NBA", "kickoff": "2026-04-26T21:00:00Z", "status": "upcoming"},
    ],
    "tennis": [
        {"id": "evt-020", "home": "Djokovic", "away": "Alcaraz", "league": "ATP Masters", "kickoff": "2026-04-25T14:00:00Z", "status": "live"},
        {"id": "evt-021", "home": "Sinner", "away": "Medvedev", "league": "ATP Masters", "kickoff": "2026-04-26T16:00:00Z", "status": "upcoming"},
    ],
    "horse_racing": [
        {"id": "evt-030", "home": "Ascot - 3:15 Race", "away": "8 runners", "league": "Royal Ascot", "kickoff": "2026-04-25T15:15:00Z", "status": "upcoming"},
    ],
    "esports": [
        {"id": "evt-040", "home": "T1", "away": "Gen.G", "league": "LCK", "kickoff": "2026-04-25T12:00:00Z", "status": "live"},
    ],
}

ODDS = {
    "evt-001": {"homeWin": 2.10, "draw": 3.40, "awayWin": 3.20},
    "evt-002": {"homeWin": 1.85, "draw": 3.60, "awayWin": 4.00},
    "evt-003": {"homeWin": 1.70, "draw": 3.80, "awayWin": 4.50},
    "evt-010": {"homeWin": 1.90, "awayWin": 1.95, "overTotal": 1.85, "underTotal": 2.00},
    "evt-011": {"homeWin": 2.20, "awayWin": 1.70, "overTotal": 1.90, "underTotal": 1.95},
    "evt-020": {"homeWin": 1.60, "awayWin": 2.30},
    "evt-021": {"homeWin": 1.75, "awayWin": 2.10},
    "evt-030": {"runner1": 3.50, "runner2": 5.00, "runner3": 7.00, "runner4": 8.50, "runner5": 12.00},
    "evt-040": {"homeWin": 1.45, "awayWin": 2.70},
}

PROMOTIONS = [
    {"id": "promo-001", "name": "Welcome Bonus", "description": "100% match on first deposit up to $200", "minDeposit": 10, "expires": "2026-05-31"},
    {"id": "promo-002", "name": "Free Bet Friday", "description": "Place 3 bets on Friday, get a $10 free bet", "minOdds": 1.50, "expires": "2026-04-30"},
    {"id": "promo-003", "name": "Acca Insurance", "description": "5+ leg accumulator insurance - stake back if one leg loses", "minLegs": 5, "expires": "2026-06-30"},
    {"id": "promo-004", "name": "Enhanced Odds", "description": "Arsenal to win at 5.00 (was 2.10) - max stake $20", "eventId": "evt-001", "expires": "2026-04-25"},
]

# In-memory state (resets on cold start — fine for a mock)
BETS = {}
BALANCE = {"amount": 1000.00, "currency": "USD"}


def respond(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    method = event.get("httpMethod", "GET")
    path = event.get("path", "/")
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    body = {}
    if event.get("body"):
        body = json.loads(event["body"])

    # --- Routes ---

    # GET /sports
    if path == "/sports" and method == "GET":
        return respond(200, {"sports": SPORTS})

    # GET /sports/{sportId}/events
    if path.startswith("/sports/") and path.endswith("/events") and method == "GET":
        sport_id = path.split("/")[2]
        events = EVENTS.get(sport_id, [])
        if not events:
            return respond(404, {"error": f"No events found for sport '{sport_id}'"})
        return respond(200, {"sport": sport_id, "events": events})

    # GET /events/{eventId}/odds
    if path.startswith("/events/") and path.endswith("/odds") and method == "GET":
        event_id = path.split("/")[2]
        odds = ODDS.get(event_id)
        if not odds:
            return respond(404, {"error": f"No odds found for event '{event_id}'"})
        event_info = _find_event(event_id)
        return respond(200, {
            "eventId": event_id,
            "event": f"{event_info['home']} vs {event_info['away']}" if event_info else "Unknown",
            "odds": odds,
            "lastUpdated": datetime.utcnow().isoformat() + "Z",
        })

    # GET /events/live
    if path == "/events/live" and method == "GET":
        live = []
        for sport, events in EVENTS.items():
            for evt in events:
                if evt["status"] == "live":
                    live.append({
                        "eventId": evt["id"],
                        "sport": sport,
                        "home": evt["home"],
                        "away": evt["away"],
                        "score": _mock_score(sport),
                    })
        return respond(200, {"liveEvents": live})

    # POST /bets
    if path == "/bets" and method == "POST":
        event_id = body.get("eventId")
        selection = body.get("selection")
        stake = body.get("stake", 0)

        if not event_id or not selection:
            return respond(400, {"error": "eventId and selection are required"})

        odds = ODDS.get(event_id)
        if not odds:
            return respond(404, {"error": f"Event '{event_id}' not found"})
        if selection not in odds:
            return respond(400, {"error": f"Invalid selection '{selection}'", "validSelections": list(odds.keys())})
        if stake <= 0:
            return respond(400, {"error": "Stake must be greater than 0"})
        if stake > BALANCE["amount"]:
            return respond(400, {"error": f"Insufficient balance: ${BALANCE['amount']:.2f}"})

        bet_id = f"bet-{uuid.uuid4().hex[:8]}"
        selected_odds = odds[selection]
        potential_return = round(stake * selected_odds, 2)
        BALANCE["amount"] -= stake

        bet = {
            "betId": bet_id,
            "eventId": event_id,
            "selection": selection,
            "odds": selected_odds,
            "stake": stake,
            "potentialReturn": potential_return,
            "status": "active",
            "placedAt": datetime.utcnow().isoformat() + "Z",
        }
        BETS[bet_id] = bet
        return respond(201, {"message": "Bet placed successfully", "bet": bet, "remainingBalance": round(BALANCE["amount"], 2)})

    # GET /bets
    if path == "/bets" and method == "GET":
        bets = list(BETS.values())
        return respond(200, {"bets": bets, "totalBets": len(bets), "totalStaked": round(sum(b["stake"] for b in bets), 2)})

    # GET /bets/{betId}
    if path.startswith("/bets/") and method == "GET" and path.count("/") == 2:
        bet_id = path.split("/")[2]
        bet = BETS.get(bet_id)
        if not bet:
            return respond(404, {"error": f"Bet '{bet_id}' not found"})
        return respond(200, {"bet": bet})

    # GET /account/balance
    if path == "/account/balance" and method == "GET":
        return respond(200, {
            "balance": round(BALANCE["amount"], 2),
            "currency": BALANCE["currency"],
            "pendingBets": len([b for b in BETS.values() if b["status"] == "active"]),
        })

    # GET /promotions
    if path == "/promotions" and method == "GET":
        return respond(200, {"promotions": PROMOTIONS})

    return respond(404, {"error": f"Route not found: {method} {path}"})


def _find_event(event_id):
    for events in EVENTS.values():
        for evt in events:
            if evt["id"] == event_id:
                return evt
    return None


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
