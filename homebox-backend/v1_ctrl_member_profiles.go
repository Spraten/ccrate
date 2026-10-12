package v1

import (
	"errors"
	"net/http"

	"github.com/google/uuid"
	"github.com/hay-kot/httpkit/errchain"
	"github.com/sysadminsmedia/homebox/backend/internal/core/services"
	"github.com/sysadminsmedia/homebox/backend/internal/data/repo"
	"github.com/sysadminsmedia/homebox/backend/internal/sys/validate"
	"github.com/sysadminsmedia/homebox/backend/internal/web/adapters"
)

func boundedMemberAction(action errchain.HandlerFunc) errchain.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) error {
		r.Body = http.MaxBytesReader(w, r.Body, 100000)
		err := action(w, r)
		var size *http.MaxBytesError
		if errors.As(err, &size) {
			return validate.NewRequestError(err, http.StatusRequestEntityTooLarge)
		}
		return err
	}
}

func (ctrl *V1Controller) memberAdministration(auth services.Context) (bool, error) {
	return ctrl.repo.Groups.IsOwnerOf(auth, auth.UID, auth.GID)
}

func (ctrl *V1Controller) requireMemberAdministrator(auth services.Context) error {
	ok, err := ctrl.memberAdministration(auth)
	if err != nil {
		return err
	}
	if !ok {
		return validate.NewRequestError(errors.New("A collection owner is required to manage accounts"), http.StatusForbidden)
	}
	return nil
}

func (ctrl *V1Controller) HandleMemberAdministration() errchain.HandlerFunc {
	return adapters.Command(func(r *http.Request) (map[string]bool, error) {
		ok, err := ctrl.memberAdministration(services.NewContext(r.Context()))
		return map[string]bool{"canManage": ok}, err
	}, http.StatusOK)
}

type BadgeMemberCreate struct {
	RequestKey uuid.UUID `json:"requestKey" validate:"required"`
	Name       string    `json:"name" validate:"required,max=255"`
	Email      string    `json:"email"`
	Password   *string   `json:"password,omitempty"`
	PIN        *string   `json:"pin,omitempty"`
}

func (ctrl *V1Controller) HandleBadgeMemberCreate() errchain.HandlerFunc {
	return boundedMemberAction(adapters.Action(func(r *http.Request, body BadgeMemberCreate) (repo.MemberProfile, error) {
		auth := services.NewContext(r.Context())
		if err := ctrl.requireMemberAdministrator(auth); err != nil {
			return repo.MemberProfile{}, err
		}
		if body.Password != nil || body.PIN != nil {
			return repo.MemberProfile{}, validate.NewRequestError(errors.New("Password and PIN sign-in for badge-only people is not enabled"), http.StatusBadRequest)
		}
		return ctrl.repo.Users.CreateBadgeMember(auth, auth.GID, body.RequestKey, body.Name, body.Email)
	}, http.StatusCreated))
}

func (ctrl *V1Controller) HandleMemberProfileGet() errchain.HandlerFunc {
	return adapters.CommandID("user_id", func(r *http.Request, id uuid.UUID) (repo.MemberProfile, error) {
		auth := services.NewContext(r.Context())
		if err := ctrl.requireMemberAdministrator(auth); err != nil {
			return repo.MemberProfile{}, err
		}
		profile, err := ctrl.repo.Users.MemberProfile(auth, auth.GID, id)
		if err != nil {
			return profile, err
		}
		profile.Protected, err = ctrl.repo.Groups.IsOwnerOf(auth, id, auth.GID)
		return profile, err
	}, http.StatusOK)
}

func (ctrl *V1Controller) HandleMemberProfileUpdate() errchain.HandlerFunc {
	return boundedMemberAction(adapters.ActionID("user_id", func(r *http.Request, id uuid.UUID, body repo.MemberProfileUpdate) (repo.MemberProfile, error) {
		auth := services.NewContext(r.Context())
		if err := ctrl.requireMemberAdministrator(auth); err != nil {
			return repo.MemberProfile{}, err
		}
		protected, err := ctrl.repo.Groups.IsOwnerOf(auth, id, auth.GID)
		if err != nil {
			return repo.MemberProfile{}, err
		}
		profile, err := ctrl.repo.Users.UpdateMemberProfile(auth, auth.GID, id, body, protected)
		profile.Protected = protected
		return profile, err
	}, http.StatusOK))
}
