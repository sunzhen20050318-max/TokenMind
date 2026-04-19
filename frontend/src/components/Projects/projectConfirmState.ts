export interface ProjectConfirmContent {
  title: string;
  message: string;
  confirmLabel: string;
}

export function buildProjectConfirmContent(
  kind: 'delete-project' | 'delete-project-session',
  targetName?: string
): ProjectConfirmContent {
  if (kind === 'delete-project') {
    const projectName = targetName?.trim() || '当前项目';
    return {
      title: '删除项目',
      message: `确定删除“${projectName}”以及该项目下的所有会话吗？此操作无法撤销。`,
      confirmLabel: '删除项目',
    };
  }

  return {
    title: '删除项目会话',
    message: '确定删除当前项目中的这条会话吗？此操作无法撤销。',
    confirmLabel: '删除会话',
  };
}
