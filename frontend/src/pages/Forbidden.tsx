import { Link } from 'react-router-dom'
import { Notice } from '../components/Notice'
import { strings } from '../lib/strings'

export function Forbidden() {
  return (
    <Notice title={strings.forbidden.title}>
      <p>{strings.forbidden.body}</p>
      <Link to="/campaigns" className="mt-4 inline-block text-primary underline">
        {strings.backToCampaigns}
      </Link>
    </Notice>
  )
}
