"use client";

/**
 * A video element that can actually play the proxies.
 *
 * The proxies are HLS, and Safari is the only browser that plays HLS from a
 * `<source>` tag. Everywhere else — Chrome, Firefox, Edge, which is to say
 * nearly everybody who has opened this — the element sat there black and the
 * fallback text never showed, because the element rendered fine and simply had
 * nothing to decode.
 *
 * So: native where it exists, hls.js where it does not. Loaded on demand rather
 * than in the bundle, since a visitor on Safari should not download a media
 * engine to watch a clip their browser already handles.
 */

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";

export interface PlayerHandle {
  seek: (to: number, play?: boolean) => void;
  element: () => HTMLVideoElement | null;
}

const Player = forwardRef<
  PlayerHandle,
  {
    src: string;
    poster?: string;
    className?: string;
    onTimeUpdate?: (t: number) => void;
    onPlay?: () => void;
    onEnded?: () => void;
    onReady?: () => void;
    /** Shown instead of the video when there is no source. Say why. */
    emptyLabel?: string;
  }
>(function Player(
  { src, poster, className, onTimeUpdate, onPlay, onEnded, onReady, emptyLabel },
  ref,
) {
  const video = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const [failure, setFailure] = useState("");
  const [retry, setRetry] = useState(0);

  useImperativeHandle(ref, () => ({
    seek: (to: number, play = false) => {
      const el = video.current;
      if (!el) return;
      try {
        el.currentTime = Math.max(0, to);
      } catch {
        /* not seekable yet; the caller seeks again on ready */
      }
      if (play) void el.play().catch(() => {});
    },
    element: () => video.current,
  }));

  useEffect(() => {
    const el = video.current;
    if (!el || !src) return;
    setFailed(false);
    setFailure("");

    // Safari, and iOS anything. Native is better: hardware decode, no second
    // buffer, and no library to keep current.
    if (el.canPlayType("application/vnd.apple.mpegurl")) {
      el.src = src;
      const ready = () => onReady?.();
      const fail = () => { setFailed(true); setFailure("The proxy playlist or one of its media segments could not be loaded."); };
      el.addEventListener("loadedmetadata", ready, { once: true });
      el.addEventListener("error", fail, { once: true });
      el.load();
      return () => { el.removeEventListener("loadedmetadata", ready); el.removeEventListener("error", fail); };
    }

    let destroyed = false;
    let instance: { destroy: () => void } | null = null;

    void import("hls.js")
      .then(({ default: Hls }) => {
        if (destroyed) return;
        if (!Hls.isSupported()) {
          setFailed(true);
          return;
        }
        const hls = new Hls({ enableWorker: true, lowLatencyMode: false, manifestLoadingMaxRetry: 3, fragLoadingMaxRetry: 4 });
        let networkRecoveries = 0;
        let mediaRecoveries = 0;
        instance = hls;
        hls.loadSource(src);
        hls.attachMedia(el);
        hls.on(Hls.Events.MANIFEST_PARSED, () => onReady?.());
        hls.on(Hls.Events.ERROR, (_e, data) => {
          // Only fatal errors are worth showing. Recoverable ones happen on
          // every seek across a segment boundary and mean nothing to a viewer.
          if (!data.fatal) return;
          if (data.type === Hls.ErrorTypes.NETWORK_ERROR && networkRecoveries++ < 2) { hls.startLoad(); return; }
          if (data.type === Hls.ErrorTypes.MEDIA_ERROR && mediaRecoveries++ < 2) { hls.recoverMediaError(); return; }
          setFailure(data.type === Hls.ErrorTypes.NETWORK_ERROR ? "The proxy playlist or media segment could not be reached." : "The browser could not decode this proxy.");
          setFailed(true);
        });
      })
      .catch(() => setFailed(true));

    return () => {
      destroyed = true;
      instance?.destroy();
    };
    // onReady is intentionally not a dependency: it changes identity on every
    // render of the parent and would tear down the media engine each time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src, retry]);

  return (
    <>
      <video
        ref={video}
        className={className}
        controls
        playsInline
        preload="metadata"
        poster={poster || undefined}
        tabIndex={0}
        onTimeUpdate={(e) => onTimeUpdate?.(e.currentTarget.currentTime)}
        onPlay={onPlay}
        onEnded={onEnded}
      />
      {/* No source is not the same as a source that is not ready yet. The scene
          reel passes an empty src when no range has been chosen for a shot, and
          this blamed the encoder for a decision nobody had made. The caller
          says which it is; the honest default is neither. */}
      {!src && <p className="hint small">{emptyLabel ?? "Nothing to play here yet."}</p>}
      {failed && <p className="hint small player-error">{failure || "This clip could not be played."} <button type="button" onClick={() => setRetry((value) => value + 1)}>Retry playback</button></p>}
    </>
  );
});

export default Player;
