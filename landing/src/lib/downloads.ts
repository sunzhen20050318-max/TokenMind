/**
 * Single source of truth for the installer URLs surfaced on the landing page.
 *
 * These mirror what `versions.json` at the repo root publishes to the desktop
 * client's update channel — kept hand-written here (instead of fetched at
 * build time) because (1) the landing build runs before versions.json is
 * known to be the deployable copy, and (2) we sometimes promote a build to
 * the website that hasn't been pushed to versions.json yet (e.g. the macOS
 * package lags Windows).
 *
 * Whenever you bump versions.json, copy the same URLs here.
 */
export interface InstallerLinks {
  macos: string | null;
  windows: string | null;
}

export const INSTALLERS: InstallerLinks = {
  // Last published macOS DMG. Mac users on newer code paths will fall through
  // to this until the next universal arm64+x64 build lands.
  macos: 'https://tokenmind.oss-cn-shenzhen.aliyuncs.com/TokenMind-0.1.9-x64.dmg',
  windows:
    'https://tokenmind.oss-cn-shenzhen.aliyuncs.com/TokenMindSetup-0.1.11.exe',
};
