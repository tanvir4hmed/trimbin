"use client";

/**
 * A count and a way to the work, not the work itself.
 *
 * The full placement inbox used to render inline above the project workspace:
 * every waiting clip, with its slate frame, its evidence and its three
 * resolution buttons. That is the right screen for a handful and the wrong one
 * for a shoot day — forty clips would have pushed the actual workspace off the
 * bottom of the page, and it duplicated the same list already sitting on the
 * ingest page.
 *
 * So the workspace says how many are waiting and where to settle them. The
 * deciding happens in one place.
 */

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { paths } from "@/lib/slug";

export default function PlacementBanner({ projectId }: { projectId: number }) {
  const inbox = useQuery({
    queryKey: ["project", projectId, "placements"],
    queryFn: () => api.placementInbox(projectId),
    refetchInterval: 8000,
  });

  const waiting = inbox.data?.count ?? 0;
  if (!waiting) return null;

  return (
    <Link className="placement-banner" href={`${paths.ingest(projectId)}`}>
      <span className="placement-banner-count">{waiting}</span>
      <span>
        <b>
          {waiting === 1 ? "A clip is" : `${waiting} clips are`} uploaded but not
          placed yet
        </b>
        <small>
          They are not takes in a shot until somebody confirms where they go —
          and nothing is analysed until then.
        </small>
      </span>
      <i aria-hidden>Settle them →</i>
    </Link>
  );
}
