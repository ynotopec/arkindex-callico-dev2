export const bootCopyToClipboardButtons = (notificationContent, targetInParent, value) => {
  const successNotification = document.createElement('div')
  successNotification.classList.add('notification', 'is-success', 'hide-after-delay')
  successNotification.textContent = notificationContent

  document.querySelectorAll('.copy-to-clipboard').forEach(button => {
    button.addEventListener('click', () => {
      if (targetInParent) {
        value = button.parentElement.querySelector(targetInParent).textContent
      }
      navigator.clipboard.writeText(value)
      button.parentElement.appendChild(successNotification)
    })
  })
}
