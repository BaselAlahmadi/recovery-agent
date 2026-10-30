"""One command to run the agent once:  python -m agent.run"""
import sys

from dotenv import load_dotenv

load_dotenv()

from agent import report, tools  # noqa: E402  (needs .env loaded first)
from agent.agent import Agent  # noqa: E402


def main():
    try:
        tools.fetch_health()
    except Exception:
        sys.exit(f"Shop not reachable at {tools.SHOP_URL}. Start it first.")
    rec = Agent().run()
    path = report.write(rec)
    print(f"{rec['outcome']} | actions={[a['action'] for a in rec['actions']]} | "
          f"tokens={rec['tokens_in']}+{rec['tokens_out']} | report: {path}")


if __name__ == "__main__":
    main()
