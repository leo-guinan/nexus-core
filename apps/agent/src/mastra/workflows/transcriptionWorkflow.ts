import { Workflow, Step } from '@mastra/core/workflows';
import { transcriptionAgent } from '../agents/transcriptionAgent';
import { createLogger } from '@mastra/core/logger';
import { z } from 'zod';
import WebSocket from 'ws';

const logger = createLogger({
  name: 'TranscriptionWorkflow',
  level: 'info',
});

const handleWebSocketMessage = new Step({
  id: 'handle-websocket-message',
  description: 'Handles incoming websocket messages from transcription service',
  inputSchema: z.object({
    type: z.enum(['partial_transcript', 'final_transcript', 'named_entities', 'sentiment']),
    text: z.string().optional(),
    timestamp: z.number(),
    entities: z.array(z.any()).optional(),
    sentiment: z.record(z.any()).optional(),
  }),
  execute: async ({ input }) => {
    switch (input.type) {
      case 'partial_transcript':
        await transcriptionAgent.handlePartialTranscript(input.text!, input.timestamp);
        break;
      case 'final_transcript':
        await transcriptionAgent.handleFinalTranscript(input.text!, input.timestamp);
        break;
      case 'named_entities':
        await transcriptionAgent.handleNamedEntities(input.entities!, input.timestamp);
        break;
      case 'sentiment':
        await transcriptionAgent.handleSentiment(input.sentiment!, input.timestamp);
        break;
    }
    return { processed: true };
  },
});

const setupWebSocket = new Step({
  id: 'setup-websocket',
  description: 'Sets up websocket server for transcription events',
  inputSchema: z.void(),
  execute: async ({ mastra }) => {
    const wss = new WebSocket.Server({ port: 8001 });
    
    wss.on('connection', (ws: WebSocket) => {
      logger.info('New transcription client connected');
      
      ws.on('message', async (message: string) => {
        try {
          const data = JSON.parse(message);
          await mastra.executeStep('handle-websocket-message', data);
        } catch (error) {
          logger.error(`Error processing message: ${error}`);
        }
      });
      
      ws.on('close', () => {
        logger.info('Transcription client disconnected');
      });
      
      ws.on('error', (error: Error) => {
        logger.error(`WebSocket error: ${error}`);
      });
    });
    
    return { wss };
  },
});

export const transcriptionWorkflow = new Workflow({
  name: 'transcription-workflow',
  triggerSchema: z.void(),
})
  .step(setupWebSocket)
  .then(handleWebSocketMessage);

transcriptionWorkflow.commit(); 