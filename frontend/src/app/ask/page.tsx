import type { Metadata } from "next";
import { Suspense } from "react";
import { ChatView } from "@/components/chat/ChatView";

export const metadata: Metadata = { title: "Ask" };

export default function AskPage() {
  return (
    <Suspense>
      <ChatView chatId={null} />
    </Suspense>
  );
}
