import { createFileRoute } from "@tanstack/react-router";

const TITLE = "Prins";
const DESCRIPTION =
  "Your inbox and your voice, turned into sticky notes you approve with a button.";
const PREVIEW_IMAGE = "https://prins.henhau.no/demo/stills/hero.png";

// Public on purpose: a link to send to potential customers. It sits outside the _app layout,
// so it needs no login and can't reach any account data. It only shows the concept model.
export const Route = createFileRoute("/demo")({
  head: () => ({
    meta: [
      { title: TITLE },
      { name: "description", content: DESCRIPTION },
      { property: "og:title", content: TITLE },
      { property: "og:description", content: DESCRIPTION },
      { property: "og:image", content: PREVIEW_IMAGE },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
      { name: "theme-color", content: "#141311" },
    ],
  }),
  component: DemoPage,
});

function DemoPage() {
  return (
    <main className="fixed inset-0 bg-[#141311] p-2 sm:p-3">
      <iframe
        src="/demo/product-3d.html"
        title="Interactive 3D model of the Prins device"
        allow="fullscreen"
        className="block size-full rounded-2xl border border-white/10 bg-[#0a0807] sm:rounded-3xl"
      />
    </main>
  );
}
