import type { Project, Session } from '../../types';

interface BuildProjectSidebarTreeOptions {
  projects: Project[];
  activeProjectId: string | null;
  expandedProjectIds: string[];
  projectSessions: Session[];
}

export interface ProjectSidebarNode {
  project: Project;
  isExpanded: boolean;
  sessions: Session[];
}

export function buildProjectSidebarTree(
  options: BuildProjectSidebarTreeOptions
): ProjectSidebarNode[] {
  return options.projects.map((project) => ({
    project,
    isExpanded: options.expandedProjectIds.includes(project.id),
    sessions:
      project.id === options.activeProjectId && options.expandedProjectIds.includes(project.id)
        ? options.projectSessions
        : [],
  }));
}
