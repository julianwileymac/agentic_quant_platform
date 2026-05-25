// FeedbackWidget.tsx — "Was this helpful?" widget rendered at the
// bottom of every doc.
//
// Posts to the Cloudflare Worker at aqp_docs/workers/feedback/, which
// opens a `docs-feedback` GitHub Issue tagged with the CODEOWNERS
// team for the page. Phase 6 of the migration plan.

import React from 'react';
import { useLocation } from '@docusaurus/router';

const FEEDBACK_ENDPOINT =
  // Same-origin in production (Cloudflare Pages); resolves to
  // https://docs.aqp.fund/api/feedback.
  '/api/feedback';

type Vote = 'up' | 'down' | null;

export default function FeedbackWidget(): React.ReactElement {
  const { pathname } = useLocation();
  const [vote, setVote] = React.useState<Vote>(null);
  const [comment, setComment] = React.useState('');
  const [submitted, setSubmitted] = React.useState(false);
  const [submitting, setSubmitting] = React.useState(false);

  async function submit(): Promise<void> {
    if (!vote) return;
    setSubmitting(true);
    try {
      await fetch(FEEDBACK_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: pathname,
          vote,
          comment: comment.slice(0, 1000),
          userAgent: navigator.userAgent,
        }),
      });
      setSubmitted(true);
    } catch {
      // Worker failure does not surface to the user; the worker
      // itself swallows errors per the credential-safety rule and
      // never echoes details back. We just acknowledge.
      setSubmitted(true);
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <div className="aqp-feedback-widget">
        Thanks — we have logged this feedback for the page owner.
      </div>
    );
  }

  return (
    <div className="aqp-feedback-widget">
      <div className="aqp-was-this-helpful">
        <strong>Was this helpful?</strong>
        <button
          type="button"
          aria-pressed={vote === 'up'}
          onClick={() => setVote('up')}
        >
          👍 Yes
        </button>
        <button
          type="button"
          aria-pressed={vote === 'down'}
          onClick={() => setVote('down')}
        >
          👎 No
        </button>
      </div>
      {vote !== null && (
        <div style={{ marginTop: '0.75rem' }}>
          <label htmlFor="aqp-feedback-comment" style={{ display: 'block', marginBottom: '0.25rem' }}>
            What could be better? (optional, will not include any login info)
          </label>
          <textarea
            id="aqp-feedback-comment"
            rows={3}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            style={{ width: '100%', padding: '0.5rem', borderRadius: '0.25rem' }}
          />
          <button
            type="button"
            onClick={submit}
            disabled={submitting}
            className="button button--primary"
            style={{ marginTop: '0.5rem' }}
          >
            {submitting ? 'Sending…' : 'Send feedback'}
          </button>
        </div>
      )}
    </div>
  );
}
