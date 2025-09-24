import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agents.ui_orchestration_agent import UIOchestrationAgent

if __name__ == "__main__":
    orchestrator = UIOchestrationAgent()
    orchestrator.run()
