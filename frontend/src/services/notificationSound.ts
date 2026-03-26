let audioContext: AudioContext | null = null;
let unlockListenersInstalled = false;

function getAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const AudioContextCtor =
    window.AudioContext ||
    (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;

  if (!AudioContextCtor) {
    return null;
  }

  if (!audioContext) {
    audioContext = new AudioContextCtor();
  }

  return audioContext;
}

export async function primeNotificationSound(): Promise<void> {
  const context = getAudioContext();
  if (!context) {
    return;
  }

  if (context.state === 'suspended') {
    try {
      await context.resume();
    } catch {
      // Ignore browser autoplay failures; we'll try again on the next gesture.
    }
  }
}

export function installNotificationSoundUnlock(): void {
  if (typeof window === 'undefined' || unlockListenersInstalled) {
    return;
  }

  const unlock = () => {
    void primeNotificationSound();
  };

  window.addEventListener('pointerdown', unlock, { passive: true });
  window.addEventListener('keydown', unlock);
  unlockListenersInstalled = true;
}

export async function playReplyNotification(): Promise<void> {
  const context = getAudioContext();
  if (!context) {
    return;
  }

  if (context.state !== 'running') {
    await primeNotificationSound();
  }

  if (context.state !== 'running') {
    return;
  }

  const now = context.currentTime;
  const output = context.createGain();
  output.connect(context.destination);
  output.gain.setValueAtTime(0.55, now);

  const lowpass = context.createBiquadFilter();
  lowpass.type = 'lowpass';
  lowpass.frequency.setValueAtTime(2200, now);
  lowpass.Q.setValueAtTime(0.7, now);
  lowpass.connect(output);

  const scheduleTone = (
    frequency: number,
    startAt: number,
    duration: number,
    peakGain: number,
    type: OscillatorType = 'sine'
  ) => {
    const oscillator = context.createOscillator();
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(frequency, startAt);

    const gainNode = context.createGain();
    gainNode.gain.setValueAtTime(0.0001, startAt);
    gainNode.gain.exponentialRampToValueAtTime(peakGain, startAt + 0.018);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, startAt + duration);

    oscillator.connect(gainNode);
    gainNode.connect(lowpass);

    oscillator.start(startAt);
    oscillator.stop(startAt + duration + 0.02);

    oscillator.onended = () => {
      gainNode.disconnect();
    };
  };

  // A softer two-note chime with a faint harmonic layer.
  scheduleTone(659.25, now, 0.22, 0.022, 'sine');
  scheduleTone(987.77, now, 0.18, 0.005, 'triangle');
  scheduleTone(783.99, now + 0.12, 0.26, 0.018, 'sine');
  scheduleTone(1174.66, now + 0.12, 0.2, 0.004, 'triangle');

  window.setTimeout(() => {
    lowpass.disconnect();
    output.disconnect();
  }, 520);
}
