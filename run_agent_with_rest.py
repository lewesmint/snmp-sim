import sys
import threading
import uvicorn
import asyncio
from app.snmp_agent import SNMPAgent
import app.api

def run_snmp_agent(agent: SNMPAgent) -> None:
    """Run the SNMP agent in a separate thread with its own event loop."""
    try:
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        agent.run()
    except Exception as e:
        print(f"\nSNMP Agent ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__": # pragma: no cover
    try:
        # Create the SNMP agent
        agent = SNMPAgent()
        
        # Set the global reference for the REST API
        app.api.snmp_agent = agent
        
        # Start SNMP agent in background thread
        snmp_thread = threading.Thread(target=run_snmp_agent, args=(agent,), daemon=True)
        snmp_thread.start()
        
        print("Starting SNMP Agent with REST API...")
        print("SNMP Agent running in background")
        print("REST API available at http://localhost:8800")
        print("Press Ctrl+C to stop")
        
        # Ensure uvicorn loggers propagate to the root logger configured by AppLogger
        import logging
        for name in ("uvicorn.error", "uvicorn.access"):
            lg = logging.getLogger(name)
            # Remove uvicorn's handlers so logs propagate to root handlers
            lg.handlers = []
            lg.propagate = True

        # Start the FastAPI server
        uvicorn.run(
            "app.api:app",
            host="0.0.0.0",
            port=8800,
            reload=False,
            log_level="info",
        )
        
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
