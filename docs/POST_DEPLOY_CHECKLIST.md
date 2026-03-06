# Post-deploy checklist
- [ ] `/healthz` returns `{"ok": true}`
- [ ] Manual login works and survives refresh
- [ ] Google/Telegram login flows still complete
- [ ] Profile modal: logged-in shows tabs only
- [ ] Profile modal: logged-out shows guest card only
- [ ] Bulk return accepts comma/newline/space separated IDs
- [ ] `/api/store/manage_balance` returns JSON on invalid input, no 500 crash
- [ ] Logs contain no plaintext secrets
