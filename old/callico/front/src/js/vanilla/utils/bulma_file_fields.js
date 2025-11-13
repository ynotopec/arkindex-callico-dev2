const handleUploadedFileName = (fileLabel) => {
  // The span that will hold the file name
  const fileNameSpan = document.createElement('span')
  fileNameSpan.classList.add('file-name')

  const fileInput = fileLabel.querySelector('input[type=file]')
  fileInput.addEventListener('change', () => {
    if (!fileInput.files.length) return

    // If this is the first time a file is selected, we setup everything to properly display the name
    if (!fileLabel.contains(fileNameSpan)) {
      fileLabel.parentElement.classList.add('file', 'has-name')
      fileLabel.appendChild(fileNameSpan)
    }

    // Adding the file name at the correct place
    fileNameSpan.textContent = fileInput.files[0].name
  })
}

export const bootBulmaFileFields = (CTALabelContent) => {
  document.querySelectorAll('.control > .file-label').forEach(fileLabel => {
    handleUploadedFileName(fileLabel)

    const CTALabel = fileLabel.querySelector('.file-cta > .file-label')
    CTALabel.textContent = CTALabelContent
  })
}
