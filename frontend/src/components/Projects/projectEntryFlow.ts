export interface CreateProjectConversationOptions {
  projectId: string;
  message: string;
  generateSessionId: () => string;
  createProjectSession: (projectId: string, sessionId: string) => Promise<void>;
  queueSessionStarter: (message: string, sessionId: string) => void;
}

export async function createProjectConversation(
  options: CreateProjectConversationOptions
): Promise<string> {
  const trimmedMessage = options.message.trim();

  if (!trimmedMessage) {
    throw new Error('message cannot be empty');
  }

  const sessionId = options.generateSessionId();
  await options.createProjectSession(options.projectId, sessionId);
  options.queueSessionStarter(trimmedMessage, sessionId);

  return sessionId;
}
