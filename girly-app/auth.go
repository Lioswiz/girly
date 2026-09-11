package main

import (
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
)

// hashPassword derives a PBKDF2-HMAC-SHA256 hash. Implemented by hand so the
// app depends on the Go standard library only.
func hashPassword(password, salt string) string {
	return pbkdf2SHA256Hex([]byte(password), []byte("girly:"+salt), 12000, 32)
}

func verifyPassword(password, salt, want string) bool {
	got := pbkdf2SHA256Hex([]byte(password), []byte("girly:"+salt), 12000, 32)
	return hmac.Equal([]byte(got), []byte(want))
}

// pbkdf2SHA256Hex implements PBKDF2 (RFC 2898) over HMAC-SHA256.
func pbkdf2SHA256Hex(password, salt []byte, iter, keyLen int) string {
	prf := hmac.New(sha256.New, password)
	hashLen := prf.Size()
	blocks := (keyLen + hashLen - 1) / hashLen

	var dk []byte
	buf := make([]byte, 4)
	for block := 1; block <= blocks; block++ {
		prf.Reset()
		prf.Write(salt)
		binary.BigEndian.PutUint32(buf, uint32(block))
		prf.Write(buf)
		u := prf.Sum(nil)

		t := make([]byte, len(u))
		copy(t, u)
		for i := 1; i < iter; i++ {
			prf.Reset()
			prf.Write(u)
			u = prf.Sum(nil)
			for j := range t {
				t[j] ^= u[j]
			}
		}
		dk = append(dk, t...)
	}
	return hex.EncodeToString(dk[:keyLen])
}

// randomToken returns a hex token built from n random bytes.
func randomToken(n int) string {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return hex.EncodeToString(b)
}
