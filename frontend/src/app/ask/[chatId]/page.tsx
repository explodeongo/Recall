import type { Metadata } from "next";
import { Suspense } from "react";
import { ChatView } from "@/components/chat/ChatView";

export const metadata: Metadata = { title: "Chat" };

export default async function ChatPage({ params }: { params: Promise<{ chatId: string }> }) {
  const id = Number((await params).chatId);
  return (
    <Suspense>
      {/* Keyed so switching chats starts from a clean slate. */}
      <ChatView key={id} chatId={Number.isFinite(id) ? id : null} />
    </Suspense>
  );
}
