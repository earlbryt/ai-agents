from langgraph.graph import Graph, Subgraph
from langgraph.graph import State

class ContentGenerationSubgraph(Subgraph):
  def build(self) -> Graph:
    graph = Graph()
    graph.add_node(
      "generate_content",self.generate_content
    )
    graph.add_node(
      "review_content",self.review_content
    )
    graph.add_edge("generate_content","review_content")
    return graph
  
  def generate_content(self, state: State) -> State:
    return state
  
  def review_content(self, state: State) -> State:
    return state
