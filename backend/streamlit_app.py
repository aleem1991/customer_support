# streamlit_app.py
# Author: Suresh D R | AI Product Developer & Technology Mentor
#
# Single-file Streamlit UI. Calls the LangGraph pipeline directly --
# no separate FastAPI process needed for local development.
# Chroma loads from S3 automatically once per session (no Load button --
# the knowledge base is already built by NB02, this just connects to it).
# In Docker/Kubernetes, the same FastAPI app (src/api/main.py) is also
# packaged and exposed for any other client that wants HTTP access,
# but Streamlit itself never needs to call it over the network locally.

import streamlit as st

st.set_page_config(page_title="Customer Support Agent", page_icon="🎧", layout="wide")


@st.cache_resource(show_spinner="Connecting to knowledge base and database...")
def init_pipeline():
    """Runs once per Streamlit session. Loads the Chroma collection from S3
    and builds the LangGraph pipeline. Cached so it never re-runs on every
    button click or page interaction."""
    from src.utils.chroma_loader import load_chroma_collection
    from src.tools import database_tools
    from src.agents.pipeline import get_pipeline

    collection = load_chroma_collection()
    database_tools.set_chroma_collection(collection)
    pipeline = get_pipeline()
    return pipeline


def run_pipeline_locally(message: str, customer_id: str, channel: str) -> dict:
    """Same logic as src/agents/pipeline.run_pipeline(), called in-process
    instead of over HTTP -- this is what makes `streamlit run` the only
    command needed for local development."""
    import time
    import uuid
    from src.agents.state import SupportState

    init_pipeline()  # ensures Chroma + pipeline are ready (cached after first call)
    from src.agents.pipeline import get_pipeline

    start = time.time()
    conv_id = f"CONV_{uuid.uuid4().hex[:8].upper()}"

    initial_state = SupportState(
        message=message, channel=channel, customer_id=customer_id, conv_id=conv_id,
        customer_data={}, open_tickets=[], billing_data=[],
        churn_score=0.0, churn_category="LOW",
        customer_sentiment="NEUTRAL", sentiment_score=0.5, priority="MEDIUM",
        customer_intent="", retrieved_chunks=[], final_response="",
        actions_taken=[], escalate_to_human=False,
        guardrail_blocked=False, block_reason="",
    )

    pipeline = get_pipeline()
    result = pipeline.invoke(initial_state)
    elapsed = round(time.time() - start, 2)

    return {
        "conv_id": conv_id,
        "customer_name": result.get("customer_data", {}).get("name", ""),
        "account_type": result.get("customer_data", {}).get("account_type", ""),
        "intent": result.get("customer_intent", ""),
        "sentiment": result.get("customer_sentiment", ""),
        "churn_score": result.get("churn_score", 0),
        "churn_category": result.get("churn_category", ""),
        "priority": result.get("priority", ""),
        "response": result.get("final_response", ""),
        "actions_taken": result.get("actions_taken", []),
        "escalated": result.get("escalate_to_human", False),
        "blocked": result.get("guardrail_blocked", False),
        "block_reason": result.get("block_reason", ""),
        "elapsed_seconds": elapsed,
    }


st.title("🎧 Intelligent Customer Support Agent")
st.caption("Suresh D R | AI Product Developer & Technology Mentor")

# Initialise once -- shows the spinner only on first load, then it's cached
try:
    init_pipeline()
    st.success("✅ Connected to knowledge base and database", icon="✅")
except Exception as e:
    st.error(f"Startup failed: {e}")
    st.info(
        "Check that NB01 has loaded the RDS tables and NB02 has uploaded "
        "the Chroma collection to S3 before running this app."
    )
    st.stop()

st.divider()

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Customer")
    customer_id = st.text_input("Customer ID", value="CUST_1000")
    channel = st.selectbox("Channel", ["web", "whatsapp", "voice", "mobile"])

    st.markdown("**Sample customers to try:**")
    st.code("CUST_1000\nCUST_1050\nCUST_1075\nCUST_1100", language=None)

with col2:
    st.subheader("Message")
    message = st.text_area(
        "Type the customer's message",
        height=120,
        placeholder="e.g. I was charged twice for my November bill...",
    )

    if st.button("Send", type="primary", use_container_width=True):
        if not message.strip():
            st.warning("Please type a message first.")
        else:
            with st.spinner("Running pipeline..."):
                try:
                    result = run_pipeline_locally(message, customer_id, channel)
                    st.session_state["last_result"] = result
                except Exception as e:
                    st.error(f"Pipeline error: {e}")

if "last_result" in st.session_state:
    r = st.session_state["last_result"]
    st.divider()

    if r.get("blocked"):
        st.error(f"🛑 Message blocked: {r.get('block_reason')}")
    else:
        badge_color = {
            "POSITIVE": "🟢", "NEUTRAL": "🟡",
            "NEGATIVE": "🟠", "VERY_NEGATIVE": "🔴",
        }.get(r.get("sentiment"), "⚪")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Intent", r.get("intent", "—"))
        c2.metric("Sentiment", f"{badge_color} {r.get('sentiment','—')}")
        c3.metric("Churn Risk", f"{r.get('churn_category','—')} ({r.get('churn_score',0)})")
        c4.metric("Priority", r.get("priority", "—"))

        st.markdown("**Response:**")
        st.info(r.get("response", ""))

        if r.get("escalated"):
            st.warning("🚨 Escalated to a human agent")

        if r.get("actions_taken"):
            st.markdown("**Actions taken:**")
            for action in r["actions_taken"]:
                st.json(action)

        st.caption(f"Response time: {r.get('elapsed_seconds')}s | Conversation: {r.get('conv_id')}")
