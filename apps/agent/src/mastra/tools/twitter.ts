import { createTool } from '@mastra/core/tools';
import { z } from 'zod';
import { TwitterApi } from 'twitter-api-v2';

type Context = {
  text: string;
  replyToTweetId?: string;
  mediaIds?: string[];
};

export const twitterTool = createTool({
  id: 'send-tweet',
  description: 'Send tweets using the Twitter API v2. Can create new tweets or reply to existing ones.',
  inputSchema: z.object({
    text: z.string(),
    replyToTweetId: z.string(),
    mediaIds: z.array(z.string())
  }),
  outputSchema: z.object({
    success: z.boolean(),
    tweetId: z.string().optional(),
    tweetUrl: z.string().optional(),
    error: z.string().optional(),
    debug: z.string().optional(),
  }).describe('Result of the tweet operation'),
  execute: async ({ context }: { context: Context }) => {
      
    if (!process.env.TWITTER_API_KEY || 
        !process.env.TWITTER_API_SECRET || 
        !process.env.TWITTER_ACCESS_TOKEN || 
        !process.env.TWITTER_ACCESS_SECRET) {
      return {
        success: false,
        error: 'Missing Twitter API credentials',
        debug: 'Required environment variables: TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET'
      };
    }

    try {
      const client = new TwitterApi({
        appKey: process.env.TWITTER_API_KEY,
        appSecret: process.env.TWITTER_API_SECRET,
        accessToken: process.env.TWITTER_ACCESS_TOKEN,
        accessSecret: process.env.TWITTER_ACCESS_SECRET,
      });

      const tweetParams: any = {
        text: context.text,
        ...(context.replyToTweetId && { reply: { in_reply_to_tweet_id: context.replyToTweetId } })
      };

      if (context.mediaIds?.length) {
        // Convert array to tuple type that Twitter API expects
        const mediaIdsTuple = context.mediaIds as [string, ...string[]];
        tweetParams.media = { media_ids: mediaIdsTuple };
      }

      const tweet = await client.v2.tweet(context.text, tweetParams);

      return {
        success: true,
        tweetId: tweet.data.id,
        tweetUrl: `https://twitter.com/i/web/status/${tweet.data.id}`,
        debug: 'Tweet sent successfully'
      };
    } catch (error) {
      console.error('Error in Twitter tool:', error);
      let errorMessage = 'Unknown error occurred';
      
      if (error instanceof Error) {
        if ('code' in error && error.code === 401) {
          errorMessage = 'Twitter authentication failed. Please verify:\n' +
            '1. Your API key and secret match\n' +
            '2. Your access token and secret match\n' +
            '3. The tokens are not expired/revoked\n' +
            '4. The tokens have the right permissions (read/write)';
        } else {
          errorMessage = error.message;
        }
      }
      
      return {
        success: false,
        error: errorMessage,
        debug: `Full error: ${JSON.stringify(error, null, 2)}`
      };
    }
  }
}); 