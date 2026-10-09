import test from 'node:test'
import assert from 'node:assert/strict'
import { externalUrl, externalPaperUrl, scholarUrl, sourceUrl } from '../src/paperLinks.js'

const saved = 'https://scholar.google.com/scholar?as_q=&num=10&btnG=Search+Scholar&as_epq=Model+Change+for+Description+Logic+Concepts&as_oq=&as_eq=&as_occt=any&as_sauthors=Ozaki'
test('prefer the exact source-provided Scholar URL, including author conditions', () => {
  assert.equal(scholarUrl({ title: 'Model Change for Description Logic Concepts', discovery_url: saved }), saved)
  assert.equal(scholarUrl({ title: 'A title' }, [{ discovery_url: saved }]), saved)
  assert.equal(scholarUrl({ title: 'A title', paper_url: saved }), saved)
  assert.equal(externalPaperUrl({ paper_url: saved }), '')
})
test('fallback encodes exact full titles and does not guess authors', () => {
  const link = new URL(scholarUrl({ title: '标题 & + "Paper" / Memory', authors_raw: 'Ana Ozaki, Oslo' }))
  assert.equal(link.hostname, 'scholar.google.com')
  assert.equal(link.searchParams.get('as_epq'), '标题 & + "Paper" / Memory')
  assert.equal(link.searchParams.get('as_sauthors'), '')
  assert.equal(scholarUrl({ title: '' }), '')
  assert.notEqual(scholarUrl({ title: 'Safe', discovery_url: 'https://evil.example/scholar' }), 'https://evil.example/scholar')
})
test('never expose local, same-site, credential-bearing or executable paper links', () => {
  for (const link of ['/uploads/paper.pdf', 'file:///D:/paper.pdf', 'javascript:alert(1)', 'data:application/pdf,xxx',
    'https://47.107.172.42/paper.pdf', 'http://127.0.0.1/paper.pdf', 'http://localhost/paper.pdf',
    'http://192.168.1.1/paper.pdf', 'http://[::1]/paper.pdf', 'https://user:pass@example.com/paper.pdf']) {
    assert.equal(externalPaperUrl({ paper_url: link }), '', link)
  }
  assert.equal(externalUrl('https://awards.example/paper.pdf', 'awards.example'), '')
  assert.equal(externalUrl('https://awards.example./paper.pdf', 'awards.example'), '')
})
test('retain external PDF/DOI links without proxying or turning awards into paper downloads', () => {
  assert.equal(externalPaperUrl({ paper_url: 'https://arxiv.org/pdf/2601.00001' }), 'https://arxiv.org/pdf/2601.00001')
  assert.equal(externalPaperUrl({ paper_url: 'https://doi.org/10.1/example' }), 'https://doi.org/10.1/example')
  assert.equal(sourceUrl({ sources: [{ url: '/uploads/local.pdf' }, { url: 'https://aaai.org/awards' }] }), 'https://aaai.org/awards')
  assert.equal(externalPaperUrl({ sources: [{ url: 'https://aaai.org/awards' }] }), '')
})
