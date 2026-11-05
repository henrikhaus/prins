import { createFileRoute } from "@tanstack/react-router";

import { PageHeader } from "@/components/app-shell";

// Temporary, for showing customers the product. To remove it: delete this file, the nav entry
// in app-shell.tsx, and public/demo/. The page is a copy of demo/product-3d/index.html.
export const Route = createFileRoute("/_app/product")({
  head: () => ({ meta: [{ title: "3D model - Prins" }] }),
  component: ProductPage,
});

function ProductPage() {
  return (
    <>
      <PageHeader
        title="3D model"
        description="Concept design. Drag to turn it, and try the three keys."
      />
      <iframe
        src="/demo/product-3d.html"
        title="Interactive 3D model of the Prins device"
        className="h-[75svh] min-h-[28rem] w-full rounded-xl border bg-card"
      />
    </>
  );
}
