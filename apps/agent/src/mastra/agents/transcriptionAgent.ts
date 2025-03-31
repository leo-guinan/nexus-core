import { openai } from '@ai-sdk/openai';
import { Agent } from '@mastra/core/agent';
import { handleTranscriptionEvent, storeTranscript, analyzeSentiment } from '../tools/transcriptionTools';

export const transcriptionAgent = new Agent({
  name: 'transcription',
  tools: {handleTranscriptionEvent, storeTranscript, analyzeSentiment},
  instructions: 'Handles real-time transcription events and reactions',
  model: openai('gpt-4o-mini'),
}); 