"""
frontend/app.py
------------------
A simple Streamlit frontend for PingMe. This is just an API CLIENT -- it
doesn't store any data itself, it only calls the FastAPI backend
(app/main.py) over HTTP, the same way Swagger's /docs page does, just with
nicer forms instead of a raw JSON editor.

Run it with:  streamlit run frontend/app.py
(Make sure your FastAPI backend is already running separately first --
this app talks to it over HTTP, it doesn't replace it.)
"""

import requests
import streamlit as st

# Change this once, later, to your deployed Render URL instead of localhost.
API_BASE_URL = "http://localhost:8000"

st.set_page_config(page_title="PingMe", page_icon="🔔")


# ---------- Session state setup ----------
# Streamlit re-runs this whole script top-to-bottom on every click, so
# anything that needs to "remember" something between clicks (like whether
# you're logged in) has to live in st.session_state, not a normal variable.
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None


def auth_headers():
    """Small helper so every authenticated request doesn't repeat this line."""
    return {"Authorization": f"Bearer {st.session_state.access_token}"}


# ---------- Screen 1: not logged in yet ----------
def show_login_page():
    st.title("🔔 PingMe")
    st.caption("Ping me when X happens.")

    tab_login, tab_register = st.tabs(["Log in", "Register"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in")

        if submitted:
            response = requests.post(
                f"{API_BASE_URL}/auth/login",
                json={"email": email, "password": password},
            )
            if response.status_code == 200:
                st.session_state.access_token = response.json()["access_token"]
                st.session_state.user_email = email
                st.rerun()  # re-run the script so it now shows the logged-in view
            else:
                st.error(response.json().get("detail", "Login failed"))

    with tab_register:
        with st.form("register_form"):
            email = st.text_input("Email", key="register_email")
            password = st.text_input("Password", type="password", key="register_password")
            submitted = st.form_submit_button("Register")

        if submitted:
            response = requests.post(
                f"{API_BASE_URL}/auth/register",
                json={"email": email, "password": password},
            )
            if response.status_code == 200:
                st.success("Account created! Now log in using the Log in tab.")
            else:
                st.error(response.json().get("detail", "Registration failed"))


# ---------- Screen 2: logged in ----------
def show_dashboard():
    st.title("🔔 PingMe")
    st.caption(f"Logged in as {st.session_state.user_email}")

    if st.sidebar.button("Log out"):
        st.session_state.access_token = None
        st.session_state.user_email = None
        st.rerun()

    show_telegram_section()
    st.divider()
    show_create_trigger_section()
    st.divider()
    show_triggers_list_section()


def show_telegram_section():
    st.subheader("Connect Telegram")
    st.caption(
        "Paste the chat_id you got from the getUpdates URL after messaging "
        "your bot. This is a one-time setup."
    )
    with st.form("telegram_form"):
        chat_id = st.text_input("Your Telegram chat_id")
        submitted = st.form_submit_button("Save")

    if submitted:
        response = requests.post(
            f"{API_BASE_URL}/users/me/telegram",
            json={"chat_id": chat_id},
            headers=auth_headers(),
        )
        if response.status_code == 200:
            st.success("Telegram connected!")
        else:
            st.error(response.json().get("detail", "Something went wrong"))


def show_create_trigger_section():
    st.subheader("Create a new trigger")

    trigger_type = st.selectbox("Trigger type", ["PRICE", "AQI"])

    if trigger_type == "AQI":
        st.info(
            "Find your coordinates on [Google Maps](https://maps.google.com) -- "
            "right-click any spot, then click the lat/long numbers to copy them. "
            "Paste below as: **28.6139,77.2090** (latitude,longitude, no spaces)"
        )
        asset_label, asset_placeholder, target_label = "Latitude,Longitude", "28.6139,77.2090", "Target AQI"
    else:
        asset_label, asset_placeholder, target_label = "Asset (e.g. bitcoin, ethereum, BTC)", "bitcoin", "Target value (USD)"

    with st.form("create_trigger_form"):
        asset = st.text_input(asset_label, placeholder=asset_placeholder)
        condition = st.selectbox("Condition", ["<", ">"])
        target_value = st.number_input(target_label, min_value=0.0, step=100.0)
        submitted = st.form_submit_button("Create trigger")

    if submitted:
        response = requests.post(
            f"{API_BASE_URL}/triggers/",
            json={"trigger_type": trigger_type, "asset": asset, "condition": condition, "target_value": target_value},
            headers=auth_headers(),
        )
        if response.status_code == 200:
            st.success(f"Trigger created: ping me when {trigger_type} for {asset} {condition} {target_value}")
        else:
            st.error(response.json().get("detail", "Something went wrong"))

def show_triggers_list_section():
    st.subheader("Your triggers")

    response = requests.get(f"{API_BASE_URL}/triggers/", headers=auth_headers())
    if response.status_code != 200:
        st.error("Couldn't load your triggers.")
        return

    triggers = response.json()
    if not triggers:
        st.info("No triggers yet -- create one above.")
        return

    for trigger in triggers:
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.write(f"**{trigger['asset']}** {trigger['condition']} {trigger['target_value']}")
        with col2:
            if st.button("Check now", key=f"check_{trigger['id']}"):
                check_response = requests.post(
                    f"{API_BASE_URL}/triggers/{trigger['id']}/check",
                    headers=auth_headers(),
                )
                if check_response.status_code == 200:
                    result = check_response.json()
                    if result["fired"]:
                        st.success(f"Fired! Current price: {result['current_price']}")
                    else:
                        st.info(f"Not fired. Current price: {result['current_price']}")
                else:
                    st.error(check_response.json().get("detail", "Check failed"))
        with col3:
            if st.button("Delete", key=f"delete_{trigger['id']}"):
                requests.delete(f"{API_BASE_URL}/triggers/{trigger['id']}", headers=auth_headers())
                st.rerun()


# ---------- Entry point ----------
if st.session_state.access_token is None:
    show_login_page()
else:
    show_dashboard()


# ==============================================================================
# ROLE OF THIS FILE:
# The user-facing screen for PingMe. Every action here (login, register,
# connect Telegram, create/check/delete a trigger) is just an HTTP call to
# the SAME FastAPI endpoints you already tested through /docs -- this file
# adds no new backend logic, it only makes those endpoints usable without
# Swagger.
# ==============================================================================