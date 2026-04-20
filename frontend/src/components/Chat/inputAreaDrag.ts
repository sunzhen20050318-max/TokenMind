export function hasFileTransfer(types: ArrayLike<string> | null | undefined): boolean {
  if (!types) {
    return false;
  }
  for (let index = 0; index < types.length; index += 1) {
    if (types[index] === 'Files') {
      return true;
    }
  }
  return false;
}
