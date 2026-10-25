import type { MetadataRoute } from "next";

/** Makes Recall installable, and puts it in the phone's Share menu once installed. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Recall",
    short_name: "Recall",
    description: "Save what you read. Ask it anything later, with answers cited from your own library.",
    start_url: "/",
    display: "standalone",
    background_color: "#fcfcfe",
    theme_color: "#4f46c8",
    icons: [
      { src: "/icons/192", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/512", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/512", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    share_target: {
      action: "/save",
      method: "GET",
      params: { title: "title", text: "text", url: "url" },
    },
  };
}
