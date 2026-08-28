import { AccuracyDashboard } from "@/components/AccuracyDashboard";

export const metadata = {
  title: "Accuracy · Trimbin",
  description:
    "How often Trimbin is right, computed live from production. Published because a system that will not show its error rate is asking to be taken on faith.",
};

// Never statically rendered. The whole point of this page is that the numbers
// are read from the archive at the moment someone looks — a build-time snapshot
// would be a screenshot with extra steps.
export const dynamic = "force-dynamic";

export default function AccuracyPage() {
  return (
    <main className="shell">
      <AccuracyDashboard />
    </main>
  );
}
