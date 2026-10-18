import { useLocation, useParams } from 'react-router-dom'
import { MockDashboard } from './Dashboard'
import { MockPopup } from './Popup'
import { MockSavings } from './Savings'
import { themeFromSearch } from './themes'

/** Throwaway design-direction mockups: /mockups/:page?theme=a|b|c */
export function MockupApp() {
  const { page } = useParams()
  const { search } = useLocation()
  const theme = themeFromSearch(search)
  if (page === 'savings') return <MockSavings theme={theme} />
  if (page === 'popup') return <MockPopup theme={theme} />
  return <MockDashboard theme={theme} />
}
