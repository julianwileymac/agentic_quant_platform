import Link from "next/link";
import { Button, Result } from "antd";

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Result
        status="404"
        title="Page not found"
        subTitle="The page you are looking for does not exist or has moved."
        extra={
          <Link href="/">
            <Button type="primary">Back to home</Button>
          </Link>
        }
      />
    </div>
  );
}
