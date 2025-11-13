export const bootConfirmCampaignArchive = (confirmContent) => {
  const archiveButton = document.getElementById('archive-button')
  archiveButton.addEventListener('click', (event) => {
    const response = confirm(confirmContent)
    if (!response) event.preventDefault()
  })
}
