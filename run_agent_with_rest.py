import sys
from app.snmp_agent import SNMPAgent

if __name__ == "__main__":
    try:
        agent = SNMPAgent()
        agent.run()
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
