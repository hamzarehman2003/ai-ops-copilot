import Link from "next/link";
import { EmptyState } from "@/components/ui";

export const metadata = { title: "Not found" };

export default function NotFound() {
  return (
    <div className="py-10">
      <EmptyState
        title="Page not found"
        icon="search"
        action={
          <Link href="/" className="text-[13px] font-medium text-primary hover:underline">
            Back to the overview
          </Link>
        }
      >
        There is no page at this address.
      </EmptyState>
    </div>
  );
}
