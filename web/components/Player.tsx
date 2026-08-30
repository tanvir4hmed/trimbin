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
    onEnded?: () => void;
    onReady?: () => void;
  }
>(function Player(
  { src, poster, className, onTimeUpdate, onEnded, onReady },
  ref,
) {
  const video = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);

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

    // Safari, and iOS anything. Native is better: hardware decode, no second
    // buffer, and no library to keep current.
    if (el.canPlayType("application/vnd.apple.mpegurl")) {
      el.src = src;
      onReady?.();
      return;
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
        const hls = new Hls({ enableWorker: true, lowLatencyMode: false });
        instance = hls;
        hls.loadSource(src);
        hls.attachMedia(el);
        hls.on(Hls.Events.MANIFEST_PARSED, () => onReady?.());
        hls.on(Hls.Events.ERROR, (_e, data) => {
          // Only fatal errors are worth showing. Recoverable ones happen on
          // every seek across a segment boundary and mean nothing to a viewer.
          if (data.fatal) setFailed(true);
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
  }, [src]);

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
        onEnded={onEnded}
      />
      {failed && (
        <p className="hint small">
          This clip could not be played. The proxy may still be building.
        </p>
      )}
    </>
  );
});

export default Player;
