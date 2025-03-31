import { z } from 'zod';

// Transcription Event Types
export const TranscriptionEventSchema = z.object({
  type: z.enum(['start', 'transcript', 'end']),
  streamId: z.string(),
  timestamp: z.number(),
  data: z.object({
    text: z.string().optional(),
    confidence: z.number().optional(),
    isFinal: z.boolean().optional(),
  }),
});

export type TranscriptionEvent = z.infer<typeof TranscriptionEventSchema>;

// API Request/Response Types
export const TranscriptionRequestSchema = z.object({
  event: TranscriptionEventSchema,
});

export type TranscriptionRequest = z.infer<typeof TranscriptionRequestSchema>;

export const TranscriptionResponseSchema = z.object({
  success: z.boolean(),
  data: z.object({
    transcript: z.string(),
    sentiment: z.object({
      score: z.number(),
      label: z.enum(['positive', 'negative', 'neutral']),
    }).optional(),
  }).optional(),
  error: z.string().optional(),
});

export type TranscriptionResponse = z.infer<typeof TranscriptionResponseSchema>;

// WebSocket Message Types
export const WebSocketMessageSchema = z.object({
  type: z.enum(['transcription_event', 'error']),
  payload: z.union([TranscriptionEventSchema, z.string()]),
});

export type WebSocketMessage = z.infer<typeof WebSocketMessageSchema>; 