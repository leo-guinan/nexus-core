import { createTool } from '@mastra/core/tools';
import { z } from 'zod';

const transcriptionEventSchema = z.object({
  type: z.enum(['partial_transcript', 'final_transcript', 'named_entities', 'sentiment']),
  text: z.string().optional(),
  timestamp: z.number(),
  entities: z.array(z.any()).optional(),
  sentiment: z.record(z.any()).optional(),
});

export const handleTranscriptionEvent = createTool({
  id: 'handle-transcription-event',
  description: 'Processes transcription events and triggers appropriate actions',
  inputSchema: transcriptionEventSchema,
  outputSchema: z.object({
    processed: z.boolean(),
    action: z.string().optional(),
  }),
  execute: async ({ input }) => {
    switch (input.type) {
      case 'partial_transcript':
        if (input.text?.toLowerCase().includes('urgent')) {
          return {
            processed: true,
            action: 'urgent_keyword_detected'
          };
        }
        break;
      case 'final_transcript':
        // Add final transcript processing logic
        break;
      case 'named_entities':
        // Add named entities processing logic
        break;
      case 'sentiment':
        if (input.sentiment?.score < 0) {
          return {
            processed: true,
            action: 'negative_sentiment_detected'
          };
        }
        break;
    }
    return { processed: true };
  },
});

export const storeTranscript = createTool({
  id: 'store-transcript',
  description: 'Stores transcription data for later use',
  inputSchema: z.object({
    text: z.string(),
    timestamp: z.number(),
    type: z.enum(['partial', 'final']),
  }),
  outputSchema: z.object({
    stored: z.boolean(),
    id: z.string().optional(),
  }),
  execute: async ({ input }) => {
    // Add storage logic here
    return { stored: true };
  },
});

export const analyzeSentiment = createTool({
  id: 'analyze-sentiment',
  description: 'Analyzes sentiment of transcription text',
  inputSchema: z.object({
    text: z.string(),
    timestamp: z.number(),
  }),
  outputSchema: z.object({
    score: z.number(),
    label: z.enum(['positive', 'negative', 'neutral']),
    confidence: z.number(),
  }),
  execute: async ({ input }) => {
    // Add sentiment analysis logic here
    return {
      score: 0,
      label: 'neutral',
      confidence: 0.5
    };
  },
}); 