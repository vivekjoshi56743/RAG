// Public read-only shared conversation page — no auth required
export default async function SharedThreadPage({ params }: { params: { token: string } }) {
  // TODO: fetch /api/shared/:token (public endpoint), render read-only chat
  return <div>Shared conversation: {params.token}</div>;
}
