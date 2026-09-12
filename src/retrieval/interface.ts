export interface RetrievalResult {
  source: "messages" | "memory_items";
  rowId: number;
  content: string;
  role?: string;
  itemType?: string;
  topicKey?: string;
  userId: string;
  score: number;
}

export interface Retriever {
  searchMessages(query: string, userId: string, limit?: number): Promise<RetrievalResult[]>;
  searchMemory(query: string, userId: string, limit?: number): Promise<RetrievalResult[]>;
}
