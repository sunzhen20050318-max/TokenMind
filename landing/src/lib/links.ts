/**
 * External links surfaced in the top nav and footer. Centralised here so
 * we have one place to update when repos move or the contact mailbox
 * changes — every consumer imports from this module.
 */

export interface ExternalLinks {
  github: string;
  gitee: string;
  email: string; // bare address, the consumer prepends `mailto:` as needed
}

export const LINKS: ExternalLinks = {
  github: 'https://github.com/sunzhen20050318-max/TokenMind',
  gitee: 'https://gitee.com/sun124578963_0/TokenMind',
  email: 'sunzhen20050318@gmail.com',
};
