from langgraph.graph import MessagesState

class ResearchState(MessagesState):
    next: str

class DocumentWritingState(MessagesState):
    next: str

class HierarchyTeamState(MessagesState):
    next: str
