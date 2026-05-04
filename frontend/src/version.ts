/**
 * Frontend's record of the running app version.
 *
 * Bump this in sync with `pyproject.toml` `version` and the Inno Setup /
 * macOS spec / DMG filenames whenever you cut a release. Keeping the
 * source of truth in TypeScript means the update banner and the Settings
 * "About" panel can both read it without an API round-trip.
 */
export const APP_VERSION = '0.1.7';
