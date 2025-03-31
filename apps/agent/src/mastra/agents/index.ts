import { openai } from '@ai-sdk/openai';
import { Agent } from '@mastra/core/agent';
import { twitterTool } from '../tools/twitter';
import { githubTool } from '../tools/githubTools';

export const memeticMarketingAgent = new Agent({
  name: 'Memetic Marketing Agent',
  instructions: `
      You are a memetic marketing agent that is tasked with writing tweets.
`,
  model: openai('gpt-4o'),
  tools: {  twitterTool, githubTool },
});

