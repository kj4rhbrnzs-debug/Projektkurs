#!/usr/bin/env python3
import secrets
import random
import threading
from pathlib import Path

from flask import Flask, jsonify, make_response, request, send_from_directory

START_CREDITS = 10
CREDIT_PER_COIN = 1
WIN_REWARD = 4
WIN_CHANCE = 0.20

BASE_DIR = Path(__file__).resolve().parent
SESSION_COOKIE = "slot_session"

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")

sessions = {}
sessions_lock = threading.Lock()


def get_or_create_session_id():
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        return sid
    return secrets.token_urlsafe(24)


def get_state(sid):
    with sessions_lock:
        if sid not in sessions:
            sessions[sid] = {"credits": START_CREDITS, "best": START_CREDITS}
        return sessions[sid]


@app.get("/")
def index():
    sid = get_or_create_session_id()
    get_state(sid)
    resp = make_response(send_from_directory(BASE_DIR, "index.html"))
    resp.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="Lax", max_age=60 * 60 * 24 * 30)
    return resp


@app.get("/slot_assets/<path:filename>")
def assets(filename):
    return send_from_directory(BASE_DIR / "slot_assets", filename)


@app.get("/api/state")
def api_state():
    sid = get_or_create_session_id()
    state = get_state(sid)
    resp = make_response(jsonify(state))
    resp.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="Lax", max_age=60 * 60 * 24 * 30)
    return resp


@app.post("/api/coin")
def api_coin():
    sid = get_or_create_session_id()
    state = get_state(sid)
    with sessions_lock:
        state["credits"] += CREDIT_PER_COIN
    resp = make_response(jsonify({"ok": True, **state}))
    resp.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="Lax", max_age=60 * 60 * 24 * 30)
    return resp


@app.post("/api/reset")
def api_reset():
    sid = get_or_create_session_id()
    state = get_state(sid)
    with sessions_lock:
        state["credits"] = START_CREDITS
    resp = make_response(jsonify({"ok": True, **state}))
    resp.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="Lax", max_age=60 * 60 * 24 * 30)
    return resp


@app.post("/api/spin")
def api_spin():
    sid = get_or_create_session_id()
    state = get_state(sid)

    with sessions_lock:
        if state["credits"] <= 0:
            resp = make_response(jsonify({"ok": False, "message": "KEINE CREDITS", **state}), 400)
            resp.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="Lax", max_age=60 * 60 * 24 * 30)
            return resp

        state["credits"] -= 1
        choices = [0, 1, 2, 3, 4]
        final_reels = random.choices(choices, k=3)

        if random.random() < WIN_CHANCE:
            sym = random.choice(choices)
            final_reels = [sym, sym, sym]

        won = final_reels[0] == final_reels[1] == final_reels[2]
        if won:
            state["credits"] += WIN_REWARD
            if state["credits"] > state["best"]:
                state["best"] = state["credits"]

        payload = {
            "ok": True,
            "reels": final_reels,
            "won": won,
            "credits": state["credits"],
            "best": state["best"],
        }

    resp = make_response(jsonify(payload))
    resp.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="Lax", max_age=60 * 60 * 24 * 30)
    return resp


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=False)
