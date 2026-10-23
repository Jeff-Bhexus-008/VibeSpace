import { Link } from "react-router-dom";

import Button from "@/components/ui/Button";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-5 px-6 text-center">
      <p className="font-display text-6xl font-semibold tracking-tight text-violet">404</p>
      <h1 className="font-display text-2xl font-semibold">This page does not exist</h1>
      <p className="max-w-md text-sm text-haze">
        The link may be old, or the content it pointed at was removed.
      </p>
      <div className="flex gap-3">
        <Link to="/">
          <Button>Back home</Button>
        </Link>
        <Link to="/feed">
          <Button variant="secondary">Open the feed</Button>
        </Link>
      </div>
    </div>
  );
}