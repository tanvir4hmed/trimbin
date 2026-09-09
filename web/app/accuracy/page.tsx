import { AccuracyDashboard } from "@/components/AccuracyDashboard";

export const metadata = {
  title: "Accuracy · Trimbin",
  description:
    "Live analysis coverage and explicit human finding reviews, by project.",
};

// Never statically rendered. The whole point of this page is that the numbers
// are read from the archive at the moment someone looks — a build-time snapshot
// would be a screenshot with extra steps.
export const dynamic = "force-dynamic";

export default function AccuracyPage() {
  return (
    <main className="shell accuracy-page">
      <AccuracyDashboard />
    </main>
  );
}
