import { createTool } from '@mastra/core/tools';
import { z } from 'zod';
import { GithubIntegration } from "@mastra/github";

const githubOperationSchema = z.object({
  repository: z.string().describe('GitHub repository URL or owner/repo format'),
  branch: z.string().optional().describe('Branch to work on'),
  filePath: z.string().describe('Path to the file to create/modify'),
  content: z.string().describe('Content to write to the file'),
  commitMessage: z.string().describe('Commit message for the changes'),
});

const github = new GithubIntegration({
  config: {
    PERSONAL_ACCESS_TOKEN: process.env.GITHUB_TOKEN!,
  },
});

export const githubTool = createTool({
  id: 'github-operations',
  description: 'Performs GitHub operations like creating files and pushing changes',
  inputSchema: githubOperationSchema,
  outputSchema: z.object({
    success: z.boolean(),
    error: z.string().optional(),
  }),
  execute: async ({ context }) => {
    try {
      const client = await github.getApiClient();
      console.log('Input context:', context);
      
      // Parse repository URL to get owner and repo
      let owner, repo;
      try {
        // Try parsing as full URL first
        const repoUrl = new URL(context.repository);
        [owner, repo] = repoUrl.pathname.slice(1).split('/');
      } catch (error) {
        // Try parsing as shorthand format (owner/repo)
        [owner, repo] = context.repository.split('/');
      }

      console.log('Parsed repo info:', { owner, repo });

      if (!owner || !repo) {
        throw new Error('Invalid repository format. Use either a full URL (https://github.com/owner/repo) or shorthand format (owner/repo)');
      }

      // Remove .git suffix if present
      repo = repo.replace(/\.git$/, '');
      
      // Get the default branch if not specified
      const branch = context.branch || 'main';
      console.log('Using branch:', branch);
      
      // Get the current commit SHA
      try {
        const ref = await client.gitGetRef({
          path: {
            owner,
            repo,
            ref: `heads/${branch}`,
          },
        });
        console.log('Got ref:', ref.data);
        
        const currentSha = ref.data?.object?.sha;
        if (!currentSha) {
          throw new Error(`Could not get current commit SHA for branch ${branch}`);
        }
        console.log('Current SHA:', currentSha);
        
        // Create or update the file
        const filePath = context.filePath;
        const content = context.content;
        console.log('File info:', { filePath, contentLength: content.length });
        
        try {
          // Create or update file directly
          console.log('Attempting direct file creation...');
          try {
            const result = await client.reposCreateOrUpdateFileContents({
              path: {
                owner,
                repo,
                path: filePath.replace(/^\.\//, ''),
              },
              body: {
                message: context.commitMessage,
                content: Buffer.from(content).toString('base64'),
                branch,
                committer: {
                  name: 'GitHub Tool',
                  email: 'github-tool@example.com'
                }
              },
            });

            if (!result.data?.content) {
              // Check for permission errors first
              if (result.response?.status === 403) {
                throw new Error('GitHub token lacks required permissions. Token needs contents=write permission.');
              }
              console.error('API response missing content:', result);
              throw new Error('Failed to create file - invalid API response');
            }

            console.log('File creation successful:', result.data.content);
            return { success: true };
          } catch (error: any) {
            console.error('File creation error details:', error);
            
            // Handle specific error cases
            if (error.status === 403) {
              return {
                success: false,
                error: 'GitHub token lacks required permissions. Token needs contents=write permission.'
              };
            }
            
            if (error.status === 422 && error.message?.includes('sha')) {
              // File exists and needs SHA for update
              console.log('File exists, getting current version...');
              const currentFile = await client.reposGetContent({
                path: {
                  owner,
                  repo,
                  path: filePath,
                  ref: branch,
                },
              });
              console.log('Current file:', currentFile.data);
              
              // Handle both single file and directory responses
              const fileData = Array.isArray(currentFile.data) 
                ? currentFile.data.find(f => f.path === filePath)
                : currentFile.data;

              if (!fileData || fileData.type !== 'file' || !fileData.sha) {
                throw new Error('Invalid file response from GitHub API');
              }
              
              // Retry update with SHA
              console.log('Updating existing file with SHA:', fileData.sha);
              const updateResult = await client.reposCreateOrUpdateFileContents({
                path: {
                  owner,
                  repo,
                  path: filePath,
                },
                body: {
                  message: context.commitMessage,
                  content: Buffer.from(content).toString('base64'),
                  sha: fileData.sha,
                  branch,
                  committer: {
                    name: 'GitHub Tool',
                    email: 'github-tool@example.com'
                  }
                },
              });
              console.log('File update result:', updateResult.data);

              if (!updateResult.data) {
                throw new Error('Failed to update file - no response data');
              }
            } else {
              throw error;
            }
          }
        } catch (error: any) {
          console.log('File creation error:', error.status, error.message);
          if (error.status === 422 && error.message?.includes('sha')) {
            // File exists and needs SHA for update
            console.log('File exists, getting current version...');
            const currentFile = await client.reposGetContent({
              path: {
                owner,
                repo,
                path: filePath,
                ref: branch,
              },
            });
            console.log('Current file:', currentFile.data);
            
            // Handle both single file and directory responses
            const fileData = Array.isArray(currentFile.data) 
              ? currentFile.data.find(f => f.path === filePath)
              : currentFile.data;

            if (!fileData || fileData.type !== 'file' || !fileData.sha) {
              throw new Error('Invalid file response from GitHub API');
            }
            
            // Retry update with SHA
            console.log('Updating existing file with SHA:', fileData.sha);
            const updateResult = await client.reposCreateOrUpdateFileContents({
              path: {
                owner,
                repo,
                path: filePath,
              },
              body: {
                message: context.commitMessage,
                content: Buffer.from(content).toString('base64'),
                sha: fileData.sha,
                branch,
                committer: {
                  name: 'GitHub Tool',
                  email: 'github-tool@example.com'
                }
              },
            });
            console.log('File update result:', updateResult.data);

            if (!updateResult.data) {
              throw new Error('Failed to update file - no response data');
            }
          } else {
            throw error;
          }
        }
      } catch (error: any) {
        if (error.status === 404) {
          // Branch doesn't exist, try to get the default branch
          const repoInfo = await client.reposGet({
            path: {
              owner,
              repo,
            },
          });
          
          if (!repoInfo.data?.default_branch) {
            throw new Error('Could not determine default branch');
          }
          
          const defaultBranch = repoInfo.data.default_branch;
          
          // Retry with the default branch
          const ref = await client.gitGetRef({
            path: {
              owner,
              repo,
              ref: `heads/${defaultBranch}`,
            },
          });
          
          const currentSha = ref.data?.object?.sha;
          if (!currentSha) {
            throw new Error(`Could not get current commit SHA for default branch ${defaultBranch}`);
          }
          
          // Create or update the file
          const filePath = context.filePath;
          const content = context.content;
          
          try {
            // Create or update file directly
            await client.reposCreateOrUpdateFileContents({
              path: {
                owner,
                repo,
                path: filePath,
              },
              body: {
                message: context.commitMessage,
                content: Buffer.from(content).toString('base64'),
                branch: defaultBranch,
              },
            });
          } catch (error: any) {
            if (error.status === 422 && error.message?.includes('sha')) {
              // File exists and needs SHA for update
              const currentFile = await client.reposGetContent({
                path: {
                  owner,
                  repo,
                  path: filePath,
                  ref: defaultBranch,
                },
              });
              
              // Handle both single file and directory responses
              const fileData = Array.isArray(currentFile.data) 
                ? currentFile.data.find(f => f.path === filePath)
                : currentFile.data;

              if (!fileData || fileData.type !== 'file' || !fileData.sha) {
                throw new Error('Invalid file response from GitHub API');
              }
              
              // Retry update with SHA
              await client.reposCreateOrUpdateFileContents({
                path: {
                  owner,
                  repo,
                  path: filePath,
                },
                body: {
                  message: context.commitMessage,
                  content: Buffer.from(content).toString('base64'),
                  sha: fileData.sha,
                },
              });
            } else {
              throw error;
            }
          }
        } else {
          throw error;
        }
      }
      
      return {
        success: true,
      };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error occurred',
      };
    }
  },
}); 