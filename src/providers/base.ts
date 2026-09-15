export interface ProviderResponse {
  statusCode: number;
  content: Uint8Array;
  headers: Record<string, string>;
  mediaType: string | null;
}

export interface ProviderStream {
  statusCode: number;
  headers: Record<string, string>;
  mediaType: string | null;
  body: ReadableStream<Uint8Array> | null;
  /** Non-SSE error body for rejected (>=400) stream requests. */
  errorBody?: Uint8Array;
}

export interface AIProvider {
  chat(body: Record<string, any>): Promise<ProviderResponse>;
  responses(body: Record<string, any>): Promise<ProviderResponse>;
  models(): Promise<ProviderResponse>;
  openStream(path: string, body: Record<string, any>): Promise<ProviderStream>;
}
