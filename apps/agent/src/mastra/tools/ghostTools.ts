import { createTool } from '@mastra/core/tools';
import { z } from 'zod';

const ghostPostSchema = z.object({
  title: z.string(),
  content: z.string(),
  excerpt: z.string().optional(),
  tags: z.array(z.string()).optional(),
  status: z.enum(['draft', 'published']).default('draft'),
  featured: z.boolean().optional(),
  featuredImage: z.string().optional(),
  canonicalUrl: z.string().optional(),
});

export const ghostTool = createTool({
  id: 'ghost-publish',
  description: 'Publishes content to a Ghost blog using their Admin API',
  inputSchema: ghostPostSchema,
  outputSchema: z.object({
    success: z.boolean(),
    postId: z.string().optional(),
    postUrl: z.string().optional(),
    error: z.string().optional(),
  }),
  execute: async ({ input }) => {
    if (!process.env.GHOST_API_URL || !process.env.GHOST_ADMIN_API_KEY) {
      return {
        success: false,
        error: 'Missing Ghost API credentials',
      };
    }

    try {
      const response = await fetch(`${process.env.GHOST_API_URL}/ghost/api/admin/posts/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Ghost ${process.env.GHOST_ADMIN_API_KEY}`,
        },
        body: JSON.stringify({
          posts: [{
            title: input.title,
            html: input.content,
            excerpt: input.excerpt,
            tags: input.tags?.map(tag => ({ name: tag })),
            status: input.status,
            featured: input.featured,
            featured_image: input.featuredImage,
            canonical_url: input.canonicalUrl,
          }],
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.errors?.[0]?.message || 'Failed to create post');
      }

      const data = await response.json();
      const post = data.posts[0];

      return {
        success: true,
        postId: post.id,
        postUrl: post.url,
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred',
      };
    }
  },
}); 