export interface RetrievalResult {
  source: "messages" | "memory_items";
  rowId: number;
  content: string;
  role?: string;
  itemType?: string;
  topicKey?: string;
  conversationId: string;
  score: number;
}

export interface Retriever {
  searchMessages(query: string, conversationId: string, limit?: number): Promise<RetrievalResult[]>;
  searchMemory(query: string, conversationId: string, limit?: number): Promise<RetrievalResult[]>;
}
