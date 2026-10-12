package repo

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"image"
	_ "image/jpeg"
	_ "image/png"
	"net/http"
	"net/mail"
	"strings"
	"sync"
	"time"
	"unicode/utf8"

	"github.com/google/uuid"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent/group"
	"github.com/sysadminsmedia/homebox/backend/internal/data/ent/user"
	"github.com/sysadminsmedia/homebox/backend/internal/sys/validate"
)

// ponytail: serialize profile/settings writes on one Pi; use per-user locks if busy.
var memberProfileMu sync.Mutex

const memberProfileKey = "caciProfile"

type MemberProfile struct {
	ID        uuid.UUID `json:"id"`
	Name      string    `json:"name"`
	Email     string    `json:"email"`
	Avatar    string    `json:"avatar"`
	Notes     string    `json:"notes"`
	Mode      string    `json:"mode"`
	UpdatedAt string    `json:"updatedAt"`
	Editable  bool      `json:"editable"`
	Protected bool      `json:"protected"`
}

type MemberProfileUpdate struct {
	Name      string  `json:"name"`
	Email     string  `json:"email"`
	Avatar    string  `json:"avatar"`
	Notes     string  `json:"notes"`
	UpdatedAt string  `json:"updatedAt"`
	Password  *string `json:"password,omitempty"`
	PIN       *string `json:"pin,omitempty"`
}

func memberProfileData(u *ent.User) map[string]interface{} {
	p, _ := u.Settings[memberProfileKey].(map[string]interface{})
	return p
}

func memberProfileString(u *ent.User, key string) string {
	value, _ := memberProfileData(u)[key].(string)
	return value
}

func memberBadgeOnly(u *ent.User) bool {
	managed, _ := memberProfileData(u)["managed"].(bool)
	return managed
}

func memberPublicEmail(u *ent.User) string {
	if memberBadgeOnly(u) {
		return memberProfileString(u, "email")
	}
	return u.Email
}

func memberProfileError(message string, status int) error {
	return validate.NewRequestError(errors.New(message), status)
}

func validMemberDetails(name, email string, emailRequired bool) error {
	if name == "" {
		return memberProfileError("Enter a name of 1 to 255 characters", http.StatusBadRequest)
	}
	if len(name) > 255 {
		return memberProfileError("Name is too long. Try a shorter name.", http.StatusBadRequest)
	}
	if email == "" && !emailRequired {
		return nil
	}
	address, err := mail.ParseAddress(email)
	if err != nil || address.Address != email || len(email) > 255 {
		return memberProfileError("Enter a valid email address", http.StatusBadRequest)
	}
	return nil
}

func validMemberAvatar(value string) error {
	if value == "" {
		return nil
	}
	if len(value) > 55000 {
		return memberProfileError("Profile picture is too large", http.StatusBadRequest)
	}
	prefix, encoded, ok := strings.Cut(value, ",")
	if !ok || (prefix != "data:image/jpeg;base64" && prefix != "data:image/png;base64") {
		return memberProfileError("Use a PNG or JPEG profile picture", http.StatusBadRequest)
	}
	raw, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil || len(raw) > 40000 {
		return memberProfileError("Profile picture is too large", http.StatusBadRequest)
	}
	config, format, err := image.DecodeConfig(bytes.NewReader(raw))
	if err != nil || config.Width < 1 || config.Height < 1 || config.Width > 256 || config.Height > 256 || prefix != "data:image/"+format+";base64" {
		return memberProfileError("Use a valid picture up to 256 by 256 pixels", http.StatusBadRequest)
	}
	if _, _, err = image.Decode(bytes.NewReader(raw)); err != nil {
		return memberProfileError("Could not read this profile picture", http.StatusBadRequest)
	}
	return nil
}

func (r *UserRepository) memberRecord(ctx context.Context, gid, id uuid.UUID) (*ent.User, error) {
	return r.db.User.Query().Where(user.ID(id), user.HasGroupsWith(group.ID(gid))).WithGroups().Only(ctx)
}

func mapMemberProfile(u *ent.User, gid uuid.UUID) MemberProfile {
	editable := u.DefaultGroupID != nil && *u.DefaultGroupID == gid
	mode := "web-account"
	if memberBadgeOnly(u) {
		mode = "badge-only"
	}
	notes := ""
	if editable {
		notes = memberProfileString(u, "notes")
	}
	return MemberProfile{ID: u.ID, Name: u.Name, Email: memberPublicEmail(u), Avatar: memberProfileString(u, "avatar"), Notes: notes, Mode: mode, UpdatedAt: u.UpdatedAt.Format(time.RFC3339Nano), Editable: editable}
}

func (r *UserRepository) MemberProfile(ctx context.Context, gid, id uuid.UUID) (MemberProfile, error) {
	u, err := r.memberRecord(ctx, gid, id)
	if err != nil {
		return MemberProfile{}, err
	}
	return mapMemberProfile(u, gid), nil
}

func (r *UserRepository) CreateBadgeMember(ctx context.Context, gid, key uuid.UUID, name, email string) (MemberProfile, error) {
	memberProfileMu.Lock()
	defer memberProfileMu.Unlock()
	name = strings.TrimSpace(name)
	email = strings.ToLower(strings.TrimSpace(email))
	if key == uuid.Nil || key.Version() != 4 {
		return MemberProfile{}, memberProfileError("Use a new confirmation identifier", http.StatusBadRequest)
	}
	if err := validMemberDetails(name, email, false); err != nil {
		return MemberProfile{}, err
	}
	intent, _ := json.Marshal([]string{name, email})
	digest := sha256.Sum256(intent)
	fingerprint := hex.EncodeToString(digest[:])
	if prior, err := r.db.User.Get(ctx, key); err == nil {
		if prior.DefaultGroupID == nil || *prior.DefaultGroupID != gid || memberProfileString(prior, "creationDigest") != fingerprint {
			return MemberProfile{}, memberProfileError("This confirmation belongs to another account creation", http.StatusConflict)
		}
		return r.MemberProfile(ctx, gid, key)
	} else if !ent.IsNotFound(err) {
		return MemberProfile{}, err
	}
	profile := map[string]interface{}{"managed": true, "email": email, "creationDigest": fingerprint}
	_, err := r.createUserWithMembership(ctx, UserCreate{Name: name, Email: "badge-" + key.String() + "@caci-create.invalid", DefaultGroupID: gid}, func(q *ent.UserCreate) *ent.UserCreate {
		return q.SetID(key).SetSettings(map[string]interface{}{memberProfileKey: profile})
	})
	if err != nil {
		return MemberProfile{}, err
	}
	return r.MemberProfile(ctx, gid, key)
}

func (r *UserRepository) UpdateMemberProfile(ctx context.Context, gid, id uuid.UUID, data MemberProfileUpdate, protected bool) (MemberProfile, error) {
	memberProfileMu.Lock()
	defer memberProfileMu.Unlock()
	if data.Password != nil || data.PIN != nil {
		return MemberProfile{}, memberProfileError("Password and PIN sign-in for badge-only people is not enabled", http.StatusBadRequest)
	}
	u, err := r.memberRecord(ctx, gid, id)
	if err != nil {
		return MemberProfile{}, err
	}
	profile := mapMemberProfile(u, gid)
	if !profile.Editable {
		return MemberProfile{}, memberProfileError("This profile is managed in its primary collection", http.StatusForbidden)
	}
	if data.UpdatedAt != profile.UpdatedAt {
		return MemberProfile{}, memberProfileError("This profile changed. Reload it before saving", http.StatusConflict)
	}
	data.Name = strings.TrimSpace(data.Name)
	data.Email = strings.ToLower(strings.TrimSpace(data.Email))
	if err := validMemberDetails(data.Name, data.Email, !memberBadgeOnly(u)); err != nil {
		return MemberProfile{}, err
	}
	if utf8.RuneCountInString(data.Notes) > 1000 {
		return MemberProfile{}, memberProfileError("Keep notes under 1000 characters", http.StatusBadRequest)
	}
	if err := validMemberAvatar(data.Avatar); err != nil {
		return MemberProfile{}, err
	}
	settings := map[string]interface{}{}
	for k, v := range u.Settings {
		settings[k] = v
	}
	p := map[string]interface{}{}
	for k, v := range memberProfileData(u) {
		p[k] = v
	}
	p["email"] = data.Email
	p["avatar"] = data.Avatar
	p["notes"] = data.Notes
	settings[memberProfileKey] = p
	q := r.db.User.Update().Where(user.ID(id), user.UpdatedAtEQ(u.UpdatedAt), user.HasGroupsWith(group.ID(gid))).SetName(data.Name).SetSettings(settings)
	if !memberBadgeOnly(u) && data.Email != strings.ToLower(u.Email) {
		if protected {
			return MemberProfile{}, memberProfileError("Keep the collection owner's sign-in email unchanged here", http.StatusBadRequest)
		}
		exists, err := r.db.User.Query().Where(user.EmailEqualFold(data.Email), user.IDNEQ(id)).Exist(ctx)
		if err != nil {
			return MemberProfile{}, err
		}
		if exists {
			return MemberProfile{}, memberProfileError("This sign-in email is already in use", http.StatusConflict)
		}
		q.SetEmail(data.Email)
	}
	count, err := q.Save(ctx)
	if err != nil {
		return MemberProfile{}, err
	}
	if count != 1 {
		return MemberProfile{}, memberProfileError("This profile changed. Reload it before saving", http.StatusConflict)
	}
	return r.MemberProfile(ctx, gid, id)
}
