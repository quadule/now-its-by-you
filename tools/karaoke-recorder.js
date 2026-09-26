// The take recorder: an AudioWorklet that hands the page every block the microphone
// delivers, stamped with its frame in the AudioContext's own clock, so a take can be
// cut from the exact frame the guide started on (tools/karaoke.js). Blocks are
// gathered to about 2048 frames before they're posted, and the loudest sample of each
// feeds the page's level meter.
class TakeRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.size = 2048;
    this.buf = new Float32Array(this.size);
    this.fill = 0;
    this.frame = 0; // the frame of buf[0]
    this.peak = 0;
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    if (this.fill && this.frame + this.fill !== currentFrame) this.flush(); // a gap in the input: never splice across it
    if (!this.fill) this.frame = currentFrame;
    for (let i = 0; i < ch.length; i++) {
      this.buf[this.fill++] = ch[i];
      const a = Math.abs(ch[i]);
      if (a > this.peak) this.peak = a;
      if (this.fill === this.size) this.flush(currentFrame + i + 1);
    }
    return true;
  }

  flush(next) {
    if (!this.fill) return;
    this.port.postMessage({ frame: this.frame, samples: this.buf.slice(0, this.fill), peak: this.peak });
    this.fill = 0;
    this.peak = 0;
    if (next !== undefined) this.frame = next;
  }
}

registerProcessor("take-recorder", TakeRecorder);
