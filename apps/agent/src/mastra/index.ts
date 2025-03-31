import { Mastra } from '@mastra/core/mastra';
import { createLogger } from '@mastra/core/logger';
import { weatherWorkflow, transcriptionWorkflow } from './workflows';
import { memeticMarketingAgent } from './agents';
import { transcriptWorkflow } from './workflows/transcriptWorkflow';

export const mastra = new Mastra({
  agents: { 
    memeticMarketingAgent,
  },
  workflows: {
    transcriptWorkflow,
  },
  logger: createLogger({
    name: 'Mastra',
    level: 'info',
  }),
});
