import { Workflow, Step } from '@mastra/core/workflows';
import { z } from 'zod';
import { githubTool } from '../tools/githubTools';
import { ghostTool } from '../tools/ghostTools';

const transcriptEventSchema = z.object({
  text: z.string(),
  timestamp: z.number(),
  streamKey: z.string(),
});

const createTranscriptFile = new Step({
  id: 'create-transcript-file',
  description: 'Creates a markdown file with the transcript in the PhD repository',
  inputSchema: transcriptEventSchema,
  execute: async ({ context }) => {
    const { text, timestamp, streamKey } = context.getStepResult('trigger');
    const date = new Date(timestamp);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    
    const filePath = `build-in-public-university/livestreams/${year}/${month}/${day}-${streamKey}.md`;
    
    const content = `# Livestream Transcript - ${streamKey}
Date: ${date.toISOString()}

## Transcript

${text}
`;

    const result = await githubTool.execute({
      input: {
        repository: 'https://github.com/leo-guinan/PhD.git',
        branch: 'main',
        filePath,
        content,
        commitMessage: `Add transcript for ${streamKey}`,
        githubToken: process.env.GITHUB_TOKEN,
      }
    });

    if (!result.success) {
      throw new Error(`Failed to create transcript file: ${result.error}`);
    }

    return { success: true };
  },
});

const publishToGhost = new Step({
  id: 'publish-to-ghost',
  description: 'Publishes the transcript to Ghost blog',
  inputSchema: transcriptEventSchema,
  execute: async ({ context }) => {
    const { text, timestamp, streamKey } = context.getStepResult('trigger');
    const date = new Date(timestamp);
    const formattedDate = date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });

    const title = `Livestream Transcript: ${streamKey} - ${formattedDate}`;
    const excerpt = `Transcript from the livestream "${streamKey}" on ${formattedDate}.`;
    
    const content = `
<h1>${title}</h1>
<p><em>Originally streamed on ${formattedDate}</em></p>

<h2>Transcript</h2>
${text.split('\n').map((line: string) => `<p>${line}</p>`).join('\n')}
`;

    const result = await ghostTool.execute({
      input: {
        title,
        content,
        excerpt,
        tags: ['livestream', 'transcript', streamKey],
        status: 'draft',
        featured: false,
      }
    });

    if (!result.success) {
      throw new Error(`Failed to publish to Ghost: ${result.error}`);
    }

    return { success: true, postUrl: result.postUrl };
  },
});

export const transcriptWorkflow = new Workflow({
  name: 'transcript-workflow',
  triggerSchema: transcriptEventSchema,
})
  .step(createTranscriptFile)
  .then(publishToGhost);

transcriptWorkflow.commit(); 